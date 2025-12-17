import gzip
import shutil
from collections import defaultdict

import networkx as nx
import pandas as pd
import requests

import config
from network import BartNetwork, Segment


def fetch_or_load_data() -> pd.DataFrame:
    """
    Checks if the data file exists locally. If not, downloads it from BART.
    Returns the loaded DataFrame.
    """
    # 1. Check if file exists
    file_path = config.OD_FILEPATH

    if not file_path.exists():
        print(f"Data file not found at {file_path}")
        print("Attempting to download from BART (this may take a moment)...")

        # Construct URL
        filename = config.OD_FILE_TEMPLATE.format(year=config.TARGET_YEAR)
        url = config.OD_URL_TEMPLATE.format(year=config.TARGET_YEAR)

        try:
            # Stream download to avoid memory spikes (thanks Gemini)
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                # Save as compressed file first if needed, or read directly
                # BART usually serves .csv.gz
                temp_gz = config.DATA_DIR / filename
                with open(temp_gz, "wb") as f:
                    shutil.copyfileobj(r.raw, f)

            # If the config path expects a CSV but we downloaded a GZ, decompress
            if file_path.suffix == ".csv" and temp_gz.suffix == ".gz":
                print("Decompressing data...")
                with gzip.open(temp_gz, "rb") as f_in:
                    with open(file_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                temp_gz.unlink()  # Remove the .gz after extraction

            print("Download and extraction complete.")

        except Exception as e:
            raise RuntimeError(f"Failed to download data: {e}")

    # 2. Load Data
    print(f"Loading data from {file_path}...")
    # BART data headers are usually: Date, Hour, Origin, Destination, Trip Count
    # Set the expected columns in config for sanity
    df = pd.read_csv(file_path, names=config.OD_FILE_COLUMNS)
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

    print("Calculating shortest paths for all OD pairs...")
    path_lookup = {}
    G_route = network.routing_graph

    # Get all nodes in the routing graph
    all_nodes = list(G_route.nodes)

    # We assume passengers enter via the line that minimizes their TOTAL travel time.
    # So we look for min(path_weight) among all (Origin, L1) -> (Dest, L2).

    stations = network.stations

    for origin in stations:
        for dest in stations:
            # Step 1: pick an origin and destination

            # skip if its the same station
            if origin == dest:
                continue

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

    return path_lookup


def calculate_segment_demand(network: BartNetwork, df: pd.DataFrame) -> dict:
    """
    Main driver function.
    1. Filters data for valid periods/stations.
    2. Routes passengers using pre-calc paths.
    3. Aggregates demand onto segments.

    Returns:
        dict[(Segment, Period)] -> Total Passengers per Hour
    """

    # 1. Pre-calculate paths
    path_lookup = build_path_lookup(network)

    # 2. Filter Data
    # Only keep rows where origin/dest are in our station list
    valid_stations = network.station_set
    df = df[df["origin"].isin(valid_stations) & df["dest"].isin(valid_stations)]

    # Map Hours to Periods
    hour_to_period = config.hours_to_periods()

    # Filter for hours that exist in our definitions
    df = df[df["hour"].isin(hour_to_period.keys())].copy()
    df["period"] = df["hour"].map(hour_to_period)

    # 3. Aggregate OD Demand
    # We sum up all trips for (Origin, Dest, Period)

    # NOTE: The raw data is usually "Total trips in this hour".
    # Since our optimization period (e.g. AM) is 4 hours long,
    # We need the "Average Hourly Demand" for that period.
    # (e.g. if AM is 4 hours, and total count is 4000, rate is 1000/hr)

    # Group by O, D, Period -> Sum counts
    od_sums = df.groupby(["origin", "dest", "period"])["count"].sum().reset_index()

    # Now divide by number of hours in that period to get Rate
    def get_period_hours(row):
        return len(config.PERIOD_TO_HOURS[row["period"]])

    od_sums["hours_in_period"] = od_sums.apply(get_period_hours, axis=1)
    od_sums["passengers_per_hr"] = od_sums["count"] / od_sums["hours_in_period"]

    # 4. Assign to Segments
    # This is the meat of this function, but remarkably easy
    segment_demand = defaultdict(float)

    print("Assigning demand to segments...")
    for row in od_sums.itertuples():
        # get the segments for the origin destination pair
        path_segments = path_lookup.get((row.origin, row.dest))

        if path_segments:
            for seg in path_segments:
                # for each segment, increment the demand
                segment_demand[(seg, row.period)] += row.passengers_per_hr
        else:
            # Handle edge case where no path found (shouldn't happen in valid graph)
            raise nx.NetworkXNoPath("No path found when assigning demand to segments")

    print(f"Routing complete. Mapped demand to {len(segment_demand)} segment-periods.")
    return dict(segment_demand)
