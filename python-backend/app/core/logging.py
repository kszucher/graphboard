import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
SYSTEM_LOG_PATH = LOGS_DIR / "system.log"


def setup_logging() -> None:
    """Configures system-wide logging to output to both console and a system.log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root Logger setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers to prevent duplicates
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    # File handler for general system logs
    file_handler = logging.FileHandler(SYSTEM_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
