# Logging Configuration

A global logging system has been set up across all source files with debug/info levels.

## Files Modified

### New File: `src/logging_config.py`
Central logging configuration module with two main functions:
- `setup_logger(name, level)` - Creates and configures a logger instance
- `set_global_log_level(level)` - Sets log level across all loggers

## Changes by File

### `src/optimize.py`
**Print statements replaced with logger calls:**
- ✓ "Failed: model is infeasible" → logger.error()
- ✓ "Solution Found" → logger.info()
- ✓ Operational cost and stranded passengers output → logger.info()
- ✓ Infeasible model output → logger.error()

**Debug statements added:**
- Segment line lookup details
- Variable and constraint creation counts
- Phase 1 and Phase 2 optimization progress
- Solution extraction and processing
- Each major step of optimization pipeline

### `src/routing.py`
**Print statements replaced with logger calls:**
- ✓ Data download status → logger.info() / logger.debug()
- ✓ Decompression status → logger.info()
- ✓ "Calculating shortest paths" → logger.info()
- ✓ "Routing complete" → logger.info()

**Debug statements added:**
- Path calculation progress (every 100 paths)
- Path weights and segments
- Routing graph node counts
- Data download URLs and progress

### `src/report.py`
**Print statements replaced with logger calls:**
- ✓ "No schedule to display" → logger.warning()
- ✓ Schedule table header → logger.info()

**Debug statements added:**
- Report generation progress
- Lines at minimum frequency tracking
- Schedule data organization

## Usage

### In `__main__` block (optimize.py):
```python
from src.logging_config import set_global_log_level

# Set global log level - change to "DEBUG" for more verbose output
set_global_log_level("INFO")  # Options: "DEBUG", "INFO", "WARNING", "ERROR"

logger.info("Starting BART Schedule Optimization")
# ... rest of code
```

### Available Log Levels
- **DEBUG**: Detailed diagnostic information (path weights, variable counts, etc.)
- **INFO**: General operational information (optimization phases, data loading)
- **WARNING**: Warning messages (missing data files, etc.)
- **ERROR**: Error messages with detailed context

### Log Format
All logs follow a consistent format:
```
[LEVEL   ] module.name - message
```

Example:
```
[DEBUG   ] src.optimize - Segment RED->ORANGE served by: ['RED', 'ORANGE']
[INFO    ] src.routing - Data loaded: 150000 records
[ERROR   ] src.optimize - Phase 1 optimization failed: model is infeasible
```

## Features

✓ Global logging configuration
✓ Consistent formatting across all modules
✓ DEBUG level statements for troubleshooting
✓ INFO level for operational flow
✓ Easy to switch between DEBUG and INFO modes
✓ All print() statements replaced with logger calls
✓ Exception context logged with exc_info=True
