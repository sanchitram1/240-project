import gurobipy as gp
from gurobipy import GRB

import src.config as config
from routing import calculate_segment_demand, fetch_or_load_data
from src.logging_config import setup_logger
from src.network import BartNetwork
from src.report import print_schedule_table

logger = setup_logger(__name__)


def get_lines_on_segment(u, v):
    """
    Helper: Returns a list of line names ('RED', 'YELLOW') that physically
    travel between station u and station v.
    """
    logger.debug(f"Finding lines serving segment {u} -> {v}")
    serving_lines = []
    for line_name, stations in config.LINES.items():
        # Check if u and v appear sequentially in this line's station list
        # (We check both directions because the segment demand is directed)
        if u in stations and v in stations:
            idx_u = stations.index(u)
            idx_v = stations.index(v)
            if abs(idx_u - idx_v) == 1:
                serving_lines.append(line_name)
    logger.debug(f"Segment {u} -> {v} served by: {serving_lines}")
    return serving_lines


def run_optimization(segment_demand: dict):
    logger.info("Starting optimization...")
    logger.debug(f"Received demand data for {len(segment_demand)} segment-period pairs")

    # 1. Setup Data
    logger.debug("Setting up model data...")
    cycle_times = config.ROUND_TRIP_HOURS
    model = gp.Model("BART_Schedule_Opt")
    logger.debug(f"Round trip times: {cycle_times}")

    # Mute Gurobi output for cleaner logs
    model.setParam("OutputFlag", 0)
    logger.debug("Gurobi output muted")

    # 2. Decision Variables
    logger.debug("Creating decision variables...")
    # f[line, period, cars] = Frequency (trains per hour)
    f = {}
    var_count = 0
    for line in config.LINES:
        for period in config.PERIOD_TO_HOURS:
            for size in config.POSSIBLE_TRAIN_LENGTHS:
                # Variable: Integer number of trains per hour
                f[line, period, size] = model.addVar(
                    vtype=GRB.INTEGER, name=f"freq_{line}_{period}_{size}cars"
                )
                var_count += 1
    logger.debug(f"Created {var_count} frequency variables")

    # Unmet Demand Vars (One per segment/period)
    # u[seg, period] = Unmet Demand (pax per hour)
    logger.debug("Creating unmet demand variables...")
    u = {}
    for seg, period in segment_demand.keys():
        u[seg, period] = model.addVar(
            vtype=GRB.CONTINUOUS, lb=0.0, name=f"unmet_{seg.u}_{seg.v}_{period}"
        )
    logger.debug(f"Created {len(u)} unmet demand variables")

    # 3. Constraints
    logger.debug("Adding constraints...")

    # A. Demand Constraint
    logger.debug("Adding demand constraints...")
    # We must be able to meet demand as best as possible
    # Capacity + Unmet >= Demand
    demand_constraint_count = 0
    for (seg, period), demand_pax in segment_demand.items():
        # What specific lines are serving this segment?
        lines_here = get_lines_on_segment(seg.u, seg.v)

        if not lines_here:
            logger.error(f"{seg.u} -> {seg.v} not served on any line")
            raise ValueError(f"{seg.u} -> {seg.v} not served on any line")

        # calculate capacity
        # Capacity = Frequency * Car_Count * Pax_Per_Car
        total_capacity = gp.quicksum(
            f[line, period, size] * size * config.CAP_PER_CAR
            for line in lines_here
            for size in config.POSSIBLE_TRAIN_LENGTHS
        )

        model.addConstr(
            total_capacity + u[seg, period] >= demand_pax,
            name=f"Dem_{seg.u}_{seg.v}_{period}",
        )
        demand_constraint_count += 1
    logger.debug(f"Added {demand_constraint_count} demand constraints")

    # B. Frequency Policy
    logger.debug("Adding frequency policy constraints...")
    # We have to abide by certain minimum service policies, and cannot run more
    # trains / hour than a pre-specified maximum
    # Min <= Total Trains Per Hour <= Max
    freq_constraint_count = 0
    for line in config.LINES:
        for period in config.PERIOD_TO_HOURS:
            total_freq = gp.quicksum(
                f[line, period, size] for size in config.POSSIBLE_TRAIN_LENGTHS
            )

            # Max Frequency
            model.addConstr(
                total_freq <= config.MAX_FREQ, name=f"MaxFreq_{line}_{period}"
            )
            freq_constraint_count += 1

            # Min Frequency
            model.addConstr(
                total_freq >= config.MIN_FREQ, name=f"MinFreq_{line}_{period}"
            )
            freq_constraint_count += 1
    logger.debug(
        f"Added {freq_constraint_count} frequency constraints (min: {config.MIN_FREQ}, max: {config.MAX_FREQ})"
    )

    # C. Fleet Size
    logger.debug("Adding fleet capacity constraints...")
    # We must not use more cars than exist in the global fleet.
    # Cars Needed = Frequency * CycleTime * TrainSize
    total_fleet_available = config.FLEET_MAX
    logger.debug(f"Total fleet available: {total_fleet_available} cars")

    # for a period, for a line, for a train size: f * size * round trip = cars
    fleet_constraint_count = 0
    for period in config.PERIOD_TO_HOURS:
        total_cars_needed = gp.quicksum(
            f[line, period, size] * size * cycle_times[line]
            for line in config.LINES
            for size in config.POSSIBLE_TRAIN_LENGTHS
        )

        model.addConstr(
            total_cars_needed <= total_fleet_available, name=f"FleetCap_{period}"
        )
        fleet_constraint_count += 1
    logger.debug(f"Added {fleet_constraint_count} fleet capacity constraints")

    # 4. Objective
    logger.debug("Setting up objective functions...")
    # Priority 1: Do not leave passengers behind
    # Priority 2: Minimize operating cost

    # Cost = Car-hours
    logger.debug("Computing operational cost expression...")
    ops_cost = gp.quicksum(
        f[line, period, size]
        * size
        * cycle_times[line]
        * len(config.PERIOD_TO_HOURS[period])
        for line in config.LINES
        for period in config.PERIOD_TO_HOURS
        for size in config.POSSIBLE_TRAIN_LENGTHS
    )
    logger.debug("Computing unmet demand penalty expression...")
    unmet_penalty = gp.quicksum(u[seg, period] for seg, period in segment_demand.keys())

    # One approach is Big M:
    # model.setObjective((1000000 * unmet_penalty) + ops_cost, GRB.MINIMIZE)

    # Other approach is lexicographic
    # Phase 1: Minimize Unmet Demand
    logger.info("Phase 1: Minimizing unmet demand...")
    model.setObjective(unmet_penalty, GRB.MINIMIZE)
    model.optimize()

    if model.status != GRB.OPTIMAL:
        logger.error("Phase 1 optimization failed: model is infeasible")
        return None

    min_possible_unmet = model.objVal
    logger.info(
        f"Phase 1 complete. Minimum Unmet Demand: {min_possible_unmet:,.0f} passengers/hr"
    )

    # Now, we add this as a constraint
    logger.debug("Locking Phase 1 solution as constraint...")
    model.addConstr(unmet_penalty <= min_possible_unmet + 0.01, name="Stage1_Lock")

    # Phase 2: Minimize the Operational Cost
    logger.info("Phase 2: Minimizing operational cost (with unmet demand locked)...")
    model.setObjective(ops_cost, GRB.MINIMIZE)

    # 5. Solve
    logger.debug("Starting Phase 2 optimization...")
    model.optimize()

    if model.status == GRB.OPTIMAL:
        total_unmet = unmet_penalty.getValue()
        logger.info("Optimization successful!")
        logger.info(f"   - Operational Cost: {ops_cost.getValue():,.0f} car-hours")
        logger.info(
            f"   - Stranded Passengers: {total_unmet:,.0f} (Should be 0 if demand is satisfiable)"
        )

        logger.debug("Extracting schedule from solution...")
        schedule = {}
        for line in config.LINES:
            for period in config.PERIOD_TO_HOURS:
                for size in config.POSSIBLE_TRAIN_LENGTHS:
                    val = f[line, period, size].X
                    if val > 0:
                        schedule[(line, period, size)] = int(val)
        logger.debug(f"Schedule contains {len(schedule)} non-zero entries")

        # Extract binding constraints
        logger.debug("Identifying binding constraints...")
        binding_constraints = []
        for constr in model.getConstrs():
            if abs(constr.slack) < 1e-6:  # Numerically close to 0
                binding_constraints.append(constr.constrName)

        if binding_constraints:
            logger.info(f"Binding Constraints ({len(binding_constraints)}):")
            for constr_name in sorted(binding_constraints):
                print(f"  - {constr_name}")
        else:
            logger.info("No binding constraints found.")

        return schedule
    else:
        logger.error("Phase 2 optimization failed: model is infeasible")
        logger.debug("Computing Irreducible Inconsistent Subsystem (IIS)...")
        model.computeIIS()
        model.write("infeasible.ilp")
        logger.error("Infeasibility report written to infeasible.ilp")
        return None


if __name__ == "__main__":
    from src.logging_config import set_global_log_level

    # Set global log level - change to "DEBUG" for more verbose output
    set_global_log_level("INFO")

    logger.info("Starting BART Schedule Optimization")
    network = BartNetwork()
    logger.info("Network initialized")

    df = fetch_or_load_data()
    logger.info(f"Data loaded: {len(df)} records")

    segment_demand = calculate_segment_demand(network, df)
    logger.info(
        f"Segment demand calculated: {len(segment_demand)} segment-period pairs"
    )

    solution = run_optimization(segment_demand)

    if solution:
        logger.info("Generating schedule report...")
        print_schedule_table(solution)
    else:
        logger.error("Optimization failed - no solution to report")
