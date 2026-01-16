import logging
import os
import sys
from typing import Optional


def setup_logger(
    name: str,
    out_dir: str,
    log_file: Optional[str] = None,
    verbose: bool = False,
) -> logging.Logger:
    """
    Setup and return a configured logger.

    Args:
        name: Logger name (e.g., 'scanner', 'downloader')
        out_dir: Base output directory
        log_file: Optional custom log filename (defaults to '{name}.log')
        verbose: If True, set logging level to DEBUG
    """
    # Ensure directory exists
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)

    # File handler
    log_dir = os.path.join(out_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    file_name = log_file or f"{name}.log"
    file_handler = logging.FileHandler(
        os.path.join(log_dir, file_name),
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get an existing logger by name."""
    return logging.getLogger(name)
