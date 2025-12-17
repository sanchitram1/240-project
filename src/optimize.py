import gurobipy as gp
from gurobipy import GRB

import src.config as config
from routing import calculate_segment_demand, fetch_or_load_data
from src.network import BartNetwork


def get_lines_on_segment(u, v):
    """
    Helper: Returns a list of line names ('RED', 'YELLOW') that physically
    travel between station u and station v.
    """
    serving_lines = []
    for line_name, stations in config.LINES.items():
        # Check if u and v appear sequentially in this line's station list
        # (We check both directions because the segment demand is directed)
        if u in stations and v in stations:
            idx_u = stations.index(u)
            idx_v = stations.index(v)
            if abs(idx_u - idx_v) == 1:
                serving_lines.append(line_name)
    return serving_lines


def run_optimization(network: BartNetwork, segment_demand: dict):
    # 1. Setup Data
    cycle_times = config.ROUND_TRIP_HOURS
    model = gp.Model("BART_Schedule_Opt")

    # Mute Gurobi output for cleaner logs (optional)
    model.setParam("OutputFlag", 0)

    # 2. Decision Variables
    # f[line, period, cars] = Frequency (trains per hour)
    f = {}
    for line in config.LINES:
        for period in config.PERIOD_TO_HOURS:
            for size in config.POSSIBLE_TRAIN_LENGTHS:
                # Variable: Integer number of trains per hour
                f[line, period, size] = model.addVar(
                    vtype=GRB.INTEGER, name=f"freq_{line}_{period}_{size}cars"
                )

    # Unmet Demand Vars (One per segment/period)
    # u[seg, period] = Unmet Demand (pax per hour)
    u = {}
    for seg, period in segment_demand.keys():
        u[seg, period] = model.addVar(
            vtype=GRB.CONTINUOUS, lb=0.0, name=f"unmet_{seg.u}_{seg.v}_{period}"
        )

    # 3. Constraints

    # A. Demand Constraint
    # Capacity + Unmet >= Demand
    # If capacity is low, unmet must be high
    for (seg, period), demand_pax in segment_demand.items():
        # what lines serve this segment?
        lines_here = get_lines_on_segment(seg.u, seg.v)

        if not lines_here:
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

    # B. Frequency Policy (The "Service Level" Constraint)
    # Min <= Total Trains Per Hour <= Max
    for line in config.LINES:
        for period in config.PERIOD_TO_HOURS:
            total_freq = gp.quicksum(
                f[line, period, size] for size in config.POSSIBLE_TRAIN_LENGTHS
            )

            # Max Frequency
            model.addConstr(
                total_freq <= config.MAX_FREQ, name=f"MaxFreq_{line}_{period}"
            )

            # Min Frequency
            model.addConstr(
                total_freq >= config.MIN_FREQ, name=f"MinFreq_{line}_{period}"
            )

    # C. Fleet Size (The "Inventory" Constraint)
    # We must not use more cars than exist in the global fleet.
    # Cars Needed = Frequency * CycleTime * TrainSize
    total_fleet_available = config.FLEET_MAX

    # for a period, for a line, for a train size: f * size * round trip = cars
    for period in config.PERIOD_TO_HOURS:
        total_cars_needed = gp.quicksum(
            f[line, period, size] * size * cycle_times[line]
            for line in config.LINES
            for size in config.POSSIBLE_TRAIN_LENGTHS
        )

        model.addConstr(
            total_cars_needed <= total_fleet_available, name=f"FleetCap_{period}"
        )

    # 4. Objective
    # Priority 1: Do not leave passengers behind
    # Priority 2: Minimize operating cost

    # Cost = Car-hours
    ops_cost = gp.quicksum(
        f[line, period, size]
        * size
        * cycle_times[line]
        * len(config.PERIOD_TO_HOURS[period])
        for line in config.LINES
        for period in config.PERIOD_TO_HOURS
        for size in config.POSSIBLE_TRAIN_LENGTHS
    )

    unmet_penalty = gp.quicksum(u[seg, period] for seg, period in segment_demand.keys())

    # one approach is Big M approach:
    model.setObjective((1000000 * unmet_penalty) + ops_cost, GRB.MINIMIZE)

    # 5. Solve
    model.optimize()

    if model.status == GRB.OPTIMAL:
        total_unmet = unmet_penalty.getValue()
        print("Solution Found!")
        print(f"   - Operational Cost: {ops_cost.getValue():,.0f} car-hours")
        print(f"   - Stranded Pax:     {total_unmet:,.0f} (Should be 0 if possible)")

        schedule = {}
        for line in config.LINES:
            for period in config.PERIOD_TO_HOURS:
                for size in config.POSSIBLE_TRAIN_LENGTHS:
                    val = f[line, period, size].X
                    if val > 0:
                        schedule[(line, period, size)] = int(val)
        return schedule
    else:
        print("❌ Model Infeasible (Even with slack variables?)")
        model.computeIIS()
        model.write("infeasible.ilp")
        return None


if __name__ == "__main__":
    network = BartNetwork()
    df = fetch_or_load_data()
    segment_demand = calculate_segment_demand(network, df)
    solution = run_optimization(network, segment_demand)
    print(solution)
