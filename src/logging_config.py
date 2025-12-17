import logging
import sys


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Configure and return a logger instance with consistent formatting.

    Args:
        name: Logger name (typically __name__)
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    Returns:
        Configured logger instance
    """
    # Convert string level to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger


def set_global_log_level(level: str):
    """
    Set the global logging level for all loggers.

    Args:
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)

    # Update all existing loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(log_level)
        for handler in logging.getLogger(logger_name).handlers:
            handler.setLevel(log_level)
