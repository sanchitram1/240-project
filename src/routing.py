import gzip
import shutil
from collections import defaultdict

import networkx as nx
import pandas as pd
import requests

import config
from network import BartNetwork, Segment
from logging_config import setup_logger

logger = setup_logger(__name__)


def fetch_or_load_data() -> pd.DataFrame:
    """
    Checks if the data file exists locally. If not, downloads it from BART.
    Returns the loaded DataFrame.
    """
    # 1. Check if file exists
    file_path = config.OD_FILEPATH
    logger.debug(f"Checking for data file at {file_path}")

    if not file_path.exists():
        logger.warning(f"Data file not found at {file_path}")
        logger.info("Attempting to download from BART (this may take a moment)...")

        # Construct URL
        filename = config.OD_FILE_TEMPLATE.format(year=config.TARGET_YEAR)
        url = config.OD_URL_TEMPLATE.format(year=config.TARGET_YEAR)
        logger.debug(f"Download URL: {url}")

        try:
            # Stream download to avoid memory spikes (thanks Gemini)
            logger.debug("Starting download...")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                # Save as compressed file first if needed, or read directly
                # BART usually serves .csv.gz
                temp_gz = config.DATA_DIR / filename
                with open(temp_gz, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
                logger.debug(f"Downloaded to {temp_gz}")

            # If the config path expects a CSV but we downloaded a GZ, decompress
            if file_path.suffix == ".csv" and temp_gz.suffix == ".gz":
                logger.info("Decompressing data...")
                with gzip.open(temp_gz, "rb") as f_in:
                    with open(file_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                temp_gz.unlink()  # Remove the .gz after extraction
                logger.debug("Decompression complete")

            logger.info("Download and extraction complete.")

        except Exception as e:
            logger.error(f"Failed to download data: {e}", exc_info=True)
            raise RuntimeError(f"Failed to download data: {e}")
    else:
        logger.debug(f"Data file found at {file_path}")

    # 2. Load Data
    logger.info(f"Loading data from {file_path}...")
    # BART data headers are usually: Date, Hour, Origin, Destination, Trip Count
    # Set the expected columns in config for sanity
    df = pd.read_csv(file_path, names=config.OD_FILE_COLUMNS)
    logger.info(f"Data loaded: {len(df)} records")
    return df


def build_path_lookup(network: BartNetwork) -> dict[tuple[str, str], list[Segment]]:
    """
    Pre-calculates the shortest path for every possible OD pair in the system.

    Returns:
        dict[(origin, dest)] -> list[Segment]
    """
    # NOTE: The output here is the list of segments for the SINGLE shortest path
    # for every Origin-Destination pair.
    #
    # Crucially, the Segments are LINE-INDEPENDENT tuples of adjacent stations.
    #
    # Trivial Example: Ashby -> 19th St
    # --------------------------------
    # 1. The Routing Graph (Dijkstra) sees two options with equal weight (Cost=2):
    #    Option A: Ashby(RED) -> Macarthur(RED) -> 19th(RED)
    #    Option B: Ashby(ORANGE) -> Macarthur(ORANGE) -> 19th(ORANGE)
    #
    # 2. It picks one (say, Option A).
    #
    # 3. We strip the line info ("RED") to get the physical track usage:
    #    Output: [Segment(Ashby, Macarthur), Segment(Macarthur, 19th)]
    #
    # 4. This works bc later, the Solver sums capacity on these physical segments:
    #    Constraint: (Freq_Red * Cap) + (Freq_Orange * Cap) >= Demand,
    #       where Demand will be calculated from all paths like Ashby -> 19th St that
    #       use this segment

    logger.info("Calculating shortest paths for all OD pairs...")
    path_lookup = {}
    G_route = network.routing_graph

    # Get all nodes in the routing graph
    all_nodes = list(G_route.nodes)
    logger.debug(f"Routing graph has {len(all_nodes)} nodes")

    # We assume passengers enter via the line that minimizes their TOTAL travel time.
    # So we look for min(path_weight) among all (Origin, L1) -> (Dest, L2).

    stations = network.stations
    total_pairs = len(stations) * (len(stations) - 1)
    processed = 0

    for origin in stations:
        for dest in stations:
            # Step 1: pick an origin and destination

            # skip if its the same station
            if origin == dest:
                continue

            processed += 1
            if processed % 100 == 0:
                logger.debug(f"Processing path {processed}/{total_pairs}...")

            # Step 2: what is every possible starting and ending node in the routing
            # graph for these two stations => (origin, RED) and (origin, YELLOW)?
            start_nodes = [n for n in all_nodes if n[0] == origin]
            end_nodes = [n for n in all_nodes if n[0] == dest]

            best_path = None
            min_weight = float("inf")

            # Step 3: Calculate shortest path across all possible lines
            for s_node in start_nodes:
                for e_node in end_nodes:
                    try:
                        # E.g.:
                        # shortest_path( (origin, RED) -> (destination, GREEN) ) vs.
                        # shortest_path( (origin, RED) -> (destination, BLUE) ) vs.
                        # ... => what's the overall shortest path?
                        weight, path = nx.bidirectional_dijkstra(
                            G_route, s_node, e_node, weight="weight"
                        )

                        # Set min weight and best path
                        if weight < min_weight:
                            min_weight = weight
                            best_path = path

                    except nx.NetworkXNoPath:
                        continue

            # Step 4: Convert shortest path which is currently Node tuples into Segments
            if best_path:
                segments = []
                for i in range(len(best_path) - 1):
                    u_node = best_path[i]
                    v_node = best_path[i + 1]

                    # If stations are different, they moved! (Travel Edge)
                    # If stations are same, they transferred. (Transfer Edge - ignore
                    # for capacity)
                    if u_node[0] != v_node[0]:
                        seg = Segment(u_node[0], v_node[0])
                        segments.append(seg)

                # Step 5: Append to our dictionary
                path_lookup[(origin, dest)] = segments
                logger.debug(
                    f"Path {origin}->{dest}: {len(segments)} segments, weight {min_weight}"
                )

    logger.info(f"Path lookup complete: {len(path_lookup)} paths calculated")
    return path_lookup


def prepare_demand_data(df: pd.DataFrame, valid_stations: set) -> pd.DataFrame:
    """
    Cleans raw ridership data and converts it into an Average Hourly Demand rate
    per Origin-Destination-Period tuple.

    Logic:
    0. Focus only on weekdays to find the maximum usage
    1. Filter out stations not in our network.
    2. Map raw hours (0-23) to our periods (AM, PM, OFF).
    3. Normalize total counts by the number of days in the dataset.
    4. Normalize by the duration of the period to get 'Passengers Per Hour'.
    """
    # 1. Convert date column to datetime objects (if not already)
    df["date"] = pd.to_datetime(df["date"])

    # 2. Filter for Weekdays ONLY (Monday=0, Sunday=6)
    # We only care about Mon-Fri for Fleet Sizing
    df_clean = df[df["date"].dt.dayofweek < 5].copy()

    # 3. Filter Data (Keep only valid stations)
    df_clean = df_clean[
        df_clean["origin"].isin(valid_stations) & df_clean["dest"].isin(valid_stations)
    ]
    # 4. Map Hours to Periods
    hour_to_period = config.hours_to_periods()

    # Filter only for hours that exist in our defined periods
    df_clean = df_clean[df_clean["hour"].isin(hour_to_period.keys())]
    df_clean["period"] = df_clean["hour"].map(hour_to_period)

    # 5. Identify Normalization Factor (The "Days" Fix)
    # If the dataset covers 3 months (90 days), we must divide the total sum by 90.
    num_days = df_clean["date"].nunique()
    if num_days == 0:
        raise ValueError("Dataset contains no valid dates after filtering!")

    # 6. Aggregate Total Counts
    # Sum up every single trip in the history of the file for this (O, D, Period)
    od_sums = (
        df_clean.groupby(["origin", "dest", "period"])["count"].sum().reset_index()
    )

    # 7. Calculate Hourly Rate
    def get_period_hours(row):
        return len(config.PERIOD_TO_HOURS[row["period"]])

    # First, get the number of hours in that particular period
    od_sums["hours_in_period"] = od_sums.apply(get_period_hours, axis=1)

    # Then, normalize it by the number of hours and the number of days
    od_sums["passengers_per_hr"] = (
        od_sums["count"]
        / (od_sums["hours_in_period"] * num_days)
        * config.DEMAND_MULTIPLIER
    )

    return od_sums


def calculate_segment_demand(network: BartNetwork, df: pd.DataFrame) -> dict:
    """
    Main driver function.
    1. Filters data for valid periods/stations.
    2. Routes passengers using pre-calc paths.
    3. Aggregates demand onto segments.

    Returns:
        dict[(Segment, Period)] -> Total Passengers per Hour
    """
    logger.info("Starting segment demand calculation...")

    # 1. Pre-calculate paths
    logger.debug("Phase 1: Building path lookup...")
    path_lookup = build_path_lookup(network)

    # 2. Get data as Origin-Destination total demand
    logger.debug("Phase 2: Preparing demand data...")
    valid_stations = network.station_set
    od_sums = prepare_demand_data(df, valid_stations)
    logger.info(f"Prepared demand data: {len(od_sums)} OD pairs with demand")

    # 3. Convert OD to Segment specific demand
    logger.debug("Phase 3: Routing demand to segments...")
    segment_demand = defaultdict(float)
    total_passengers = 0

    for row in od_sums.itertuples():
        # skip same station exits (anomaly)
        if row.origin == row.dest:
            continue

        path_segments = path_lookup.get((row.origin, row.dest))

        if path_segments:
            for seg in path_segments:
                # for each segment, increment the demand
                segment_demand[(seg, row.period)] += row.passengers_per_hr
            total_passengers += row.passengers_per_hr
        else:
            # Handle edge case where no path found (shouldn't happen in valid graph)
            logger.error(f"No shortest path found for {row.origin} -> {row.dest}")
            raise nx.NetworkXNoPath(f"No shortest path for {row.origin} -> {row.dest}")

    logger.info(
        f"Segment demand calculation complete: {len(segment_demand)} segment-period pairs"
    )
    logger.info(f"Total demand routed: {total_passengers:,.0f} passengers/hour")
    return dict(segment_demand)
