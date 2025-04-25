import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else "./data"
db_path = f"{data_dir_path}/results.db"

logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Using database path: {db_path}")
logger.info(f"Database file exists: {os.path.exists(db_path)}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS results")
    
    conn.commit()
    logger.info("Results table dropped successfully")
    conn.close()
except Exception as e:
    logger.error(f"Error dropping results table: {e}")
