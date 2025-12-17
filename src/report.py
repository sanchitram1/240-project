from collections import defaultdict

import src.config as config


def print_schedule_table(schedule):
    """
    Prints a formatted matrix of the schedule.
    Rows: Lines
    Columns: Periods
    Cells: "Freq x Size" (e.g., "4x10c")

    Highlights (!) if the line is running at minimum allowed frequency.
    """
    if not schedule:
        print("No schedule to display.")
        return

    # 1. Re-organize data: grid[line][period] = [(count, size), ...]
    grid = defaultdict(lambda: defaultdict(list))

    for (line, period, size), count in schedule.items():
        grid[line][period].append((count, size))

    # 2. Sort lines and periods for consistent display
    lines = sorted(config.LINES.keys())
    periods = list(config.PERIOD_TO_HOURS.keys())  # ['AM', 'MID', 'PM', 'EVE']

    # 3. Define Column Widths
    col_width = 25
    line_col_width = 10

    # 4. Print Header
    header = f"{'LINE':<{line_col_width}} | " + " | ".join(
        [f"{p:^{col_width}}" for p in periods]
    )
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))

    # 5. Print Rows
    for line in lines:
        row_str = f"{line:<{line_col_width}} | "

        for period in periods:
            configs = grid[line][period]

            # Calculate total frequency for this cell
            total_freq = sum(c for c, s in configs) if configs else 0

            if total_freq == 0:
                # No trains scheduled
                cell_text = "0 trains (!)"
            else:
                # Sort by size (descending) for readability
                configs.sort(key=lambda x: x[1], reverse=True)

                # Format: "2x10c, 1x4c"
                parts = [f"{count}x{size}c" for count, size in configs]
                cell_text = ", ".join(parts)

                # CHECK: Is this the bare minimum frequency?
                if int(total_freq) == int(config.MIN_FREQ):
                    cell_text += " (!)"

            row_str += f"{cell_text:^{col_width}} | "

        print(row_str)

    print("=" * len(header))
    print(
        f"(!) = Service running at Policy Minimum ({config.MIN_FREQ} trains/hr). Demand did not justify this capacity."
    )
    print("\n")
