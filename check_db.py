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
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    logger.info(f"Tables in database: {[table[0] for table in tables]}")
    
    if any(table[0] == 'candidates' for table in tables):
        cursor.execute("SELECT COUNT(*) FROM candidates")
        count = cursor.fetchone()[0]
        logger.info(f"Number of records in candidates table: {count}")
        
        if count > 0:
            cursor.execute("SELECT * FROM candidates LIMIT 5")
            sample = cursor.fetchall()
            logger.info(f"Sample data: {sample}")
    
    conn.close()
except Exception as e:
    logger.error(f"Error: {e}")
