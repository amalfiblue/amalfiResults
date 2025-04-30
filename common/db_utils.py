import os
import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Get the standardized database path."""
    is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
    if is_docker:
        data_dir_path = "/app/data"
    else:
        # Get the absolute path to amalfiResults/data
        data_dir_path = str(Path(__file__).parent.parent / "data")

    db_path = str(Path(data_dir_path) / "results.db")
    logger.error(f"DB PATH BEING USED: {db_path}")  # Debug log
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
    # Convert to absolute path
    abs_path = os.path.abspath(db_path)
    logger.error(f"ABSOLUTE PATH BEING USED: {abs_path}")
    # SQLite URLs need three slashes for relative paths, four for absolute
    if abs_path.startswith("/"):
        return f"sqlite:///{abs_path}"  # Three slashes for absolute paths on Unix
    return f"sqlite:///{abs_path}"  # Three slashes for relative paths
