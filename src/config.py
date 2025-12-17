from pathlib import Path

# 1. FILE PATHS & SYSTEM SETTINGS
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
OD_FILEPATH = DATA_DIR / "date-hour-soo-dest-2025.csv"  # Updated to match your repo
RANDOM_SEED = 222


# 2. TIME & SCOPE
# We model 4 distinct periods.
# The "Representative Hour" is used to scale hourly demand to the full period.
PERIODS = ["AM", "MID", "PM", "EVE"]
PERIOD_TO_HOURS = {
    "AM": [6, 7, 8, 9],
    "MID": [10, 11, 12, 13, 14],
    "PM": [15, 16, 17, 18],
    "EVE": [19, 20, 21],
}


# 3. PHYSICAL CONSTANTS
CAP_PER_CAR = 200
FLEET_MAX = 1100  # Total cars available
POSSIBLE_TRAIN_LENGTHS = list(range(3, 11))  # [3, 4, ..., 10]

# "Laws of Physics" / Policy limits (Trains per hour)
MIN_FREQ = 2  # Max gap ~30 mins
MAX_FREQ = 12  # Min gap ~5 mins

# 4. NETWORK DEFINITIONS
# Cost of transferring between lines (in "equivalent stops" units)
TRANSFER_PENALTY_EDGES = 4
STATIONS = [
    "16TH",
    "ANTC",
    "BALB",
    "BERY",
    "CIVC",
    "COLS",
    "CONC",
    "DBRK",
    "DELN",
    "EMBR",
    "LAKE",
    "MONT",
    "PHIL",
    "PLZA",
    "POWL",
    "SHAY",
    "WOAK",
    "12TH",
    "19TH",
    "24TH",
    "DALY",
    "FTVL",
    "GLEN",
    "HAYW",
    "MCAR",
    "MLBR",
    "NBRK",
    "PITT",
    "SBRN",
    "UCTY",
    "ASHB",
    "FRMT",
    "LAFY",
    "ORIN",
    "ROCK",
    "SANL",
    "SFIA",
    "WCRK",
    "COLM",
    "SSAN",
    "WDUB",
    "BAYF",
    "NCON",
    "CAST",
    "DUBL",
    "RICH",
    "WARM",
    "PCTR",
    "OAKL",
    "MLPT",
]

LINES = {
    "RED": [
        "RICH",
        "DELN",
        "PLZA",
        "NBRK",
        "DBRK",
        "ASHB",
        "MCAR",
        "19TH",
        "12TH",
        "WOAK",
        "EMBR",
        "MONT",
        "POWL",
        "CIVC",
        "16TH",
        "24TH",
        "GLEN",
        "BALB",
        "DALY",
        "COLM",
        "SSAN",
        "SBRN",
        "SFIA",
        "MLBR",
    ],
    "ORANGE": [
        "RICH",
        "DELN",
        "PLZA",
        "NBRK",
        "DBRK",
        "ASHB",
        "MCAR",
        "19TH",
        "12TH",
        "LAKE",
        "COLS",
        "SANL",
        "BAYF",
        "HAYW",
        "SHAY",
        "UCTY",
        "FRMT",
        "WARM",
        "MLPT",
        "BERY",
    ],
    "YELLOW": [
        "ANTC",
        "PCTR",
        "PITT",
        "NCON",
        "CONC",
        "PHIL",
        "WCRK",
        "LAFY",
        "ORIN",
        "ROCK",
        "MCAR",
        "19TH",
        "12TH",
        "WOAK",
        "EMBR",
        "MONT",
        "POWL",
        "CIVC",
        "16TH",
        "24TH",
        "GLEN",
        "BALB",
        "DALY",
        "COLM",
        "SSAN",
        "SBRN",
        "SFIA",
        "MLBR",
    ],
    "GREEN": [
        "DALY",
        "BALB",
        "GLEN",
        "24TH",
        "16TH",
        "CIVC",
        "POWL",
        "MONT",
        "EMBR",
        "WOAK",
        "LAKE",
        "COLS",
        "SANL",
        "BAYF",
        "HAYW",
        "SHAY",
        "UCTY",
        "FRMT",
        "WARM",
        "MLPT",
        "BERY",
    ],
    "BLUE": [
        "DALY",
        "BALB",
        "GLEN",
        "24TH",
        "16TH",
        "CIVC",
        "POWL",
        "MONT",
        "EMBR",
        "WOAK",
        "LAKE",
        "COLS",
        "SANL",
        "BAYF",
        "CAST",
        "WDUB",
        "DUBL",
    ],
    # OAK Shuttle is exogenous (handled separately) but part of the map
    "OAK": ["COLS", "OAKL"],
}

# The lines we actually optimize (excluding the OAK shuttle)
MODEL_LINES = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE"]
DIRS = ["FWD", "REV"]


# 5. BASELINE / OPERATIONAL ASSUMPTIONS
# Round Trip Times (Hours) - Hardcoded based on historical averages
ROUND_TRIP_HOURS = {
    "YELLOW": 2.5,
    "RED": 2.4,
    "GREEN": 2.2,
    "BLUE": 2.0,
    "ORANGE": 2.3,
}

# Status Quo Frequencies (Trains/hr) - For comparison only
# (Line, Direction, Period) -> Frequency
BASELINE_FREQUENCIES = {}
for ln in MODEL_LINES:
    for dr in DIRS:
        BASELINE_FREQUENCIES[(ln, dr, "AM")] = 6 if ln == "YELLOW" else 4
        BASELINE_FREQUENCIES[(ln, dr, "MID")] = 4 if ln == "YELLOW" else 3
        BASELINE_FREQUENCIES[(ln, dr, "PM")] = 6 if ln == "YELLOW" else 4
        BASELINE_FREQUENCIES[(ln, dr, "EVE")] = 2
