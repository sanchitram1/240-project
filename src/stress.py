import src.config as config
from routing import calculate_segment_demand, fetch_or_load_data
from src.logging_config import set_global_log_level, setup_logger
from src.network import BartNetwork
from src.optimize import run_optimization
from src.report import print_schedule_table

logger = setup_logger(__name__)


def stress_test():
    """Run optimization under different stress scenarios."""

    # Load data once
    logger.info("Loading data...")
    network = BartNetwork()
    df = fetch_or_load_data()
    logger.info(f"Data loaded: {len(df)} records")

    # Define scenarios
    scenarios = [
        {
            "name": "DEFAULT",
            "demand_multiplier": 1.0,
            "min_freq": 2,
            "max_freq": 12,
            "cap_per_car": 150,
            "fleet_max": 1100,
        },
        {
            "name": "10x USAGE",
            "demand_multiplier": 10.0,
            "min_freq": 4,
            "max_freq": 20,
            "cap_per_car": 150,
            "fleet_max": 1100,
        },
        {
            "name": "EXTREME",
            "demand_multiplier": 15.0,
            "min_freq": 4,
            "max_freq": 20,
            "cap_per_car": 150,
            "fleet_max": 1500,  # otherwise it doesn't solve!
        },
    ]

    results = {}

    for scenario in scenarios:
        print("\n")
        logger.info(f"{'=' * 60}")
        logger.info(f"SCENARIO: {scenario['name']}")
        logger.info(f"{'=' * 60}")
        logger.info(f"  Demand Multiplier: {scenario['demand_multiplier']}")
        logger.info(f"  Min Frequency: {scenario['min_freq']} trains/hr")
        logger.info(f"  Max Frequency: {scenario['max_freq']} trains/hr")
        logger.info(f"  Capacity Per Car: {scenario['cap_per_car']} pax")
        logger.info(f"  Fleet Size: {scenario['fleet_max']} cars")

        # Update config values
        config.DEMAND_MULTIPLIER = scenario["demand_multiplier"]
        config.MIN_FREQ = scenario["min_freq"]
        config.MAX_FREQ = scenario["max_freq"]
        config.CAP_PER_CAR = scenario["cap_per_car"]
        config.FLEET_MAX = scenario["fleet_max"]

        # Calculate segment demand
        segment_demand = calculate_segment_demand(network, df)

        # Run optimization
        schedule = run_optimization(segment_demand)

        if schedule:
            results[scenario["name"]] = schedule
            print_schedule_table(schedule)
        else:
            results[scenario["name"]] = None

    print("\n")
    logger.info("=" * 60)
    logger.info("STRESS TEST COMPLETE")
    logger.info("=" * 60)

    for scenario_name, result in results.items():
        status = "SUCCESS" if result else "FAILED"
        logger.info(f"{scenario_name}: {status}")


if __name__ == "__main__":
    set_global_log_level("INFO")
    stress_test()
