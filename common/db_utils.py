import os
import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Get the standardized database path."""
    is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
    data_dir_path = (
        "/app/data" if is_docker else str(Path(__file__).parent.parent.parent / "data")
    )
    db_path = str(Path(data_dir_path) / "results.db")
    logger.info(f"Using database path: {db_path}")
    return db_path


def ensure_database_exists() -> None:
    """Ensure the database file exists and has the correct permissions."""
    db_path = get_db_path()
    data_dir = Path(db_path).parent

    # Create data directory if it doesn't exist
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(data_dir, 0o777)  # Full permissions for the data directory

    # Create database file if it doesn't exist
    if not os.path.exists(db_path):
        logger.info(f"Creating new database at {db_path}")
        conn = sqlite3.connect(db_path)
        conn.close()
        os.chmod(db_path, 0o666)  # Read/write permissions for the database file
        logger.info("Database file created with appropriate permissions")
    else:
        logger.info(f"Database already exists at {db_path}")


def get_sqlalchemy_url() -> str:
    """Get the SQLAlchemy URL for the database."""
    db_path = get_db_path()
    return f"sqlite:///{db_path}"
