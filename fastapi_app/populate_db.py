import sqlite3
import os
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else "./data"
db_path = f"{data_dir_path}/results.db"

logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Using database path: {db_path}")

sample_candidates = [
    {
        "candidate_name": "Jane Smith",
        "party": "Labor Party",
        "electorate": "Melbourne",
        "ballot_position": 1,
        "candidate_type": "house",
        "state": "VIC",
        "data": json.dumps({"surname": "Smith", "ballotGivenName": "Jane"})
    },
    {
        "candidate_name": "John Doe",
        "party": "Liberal Party",
        "electorate": "Melbourne",
        "ballot_position": 2,
        "candidate_type": "house",
        "state": "VIC",
        "data": json.dumps({"surname": "Doe", "ballotGivenName": "John"})
    },
    {
        "candidate_name": "Alice Johnson",
        "party": "Greens",
        "electorate": "Sydney",
        "ballot_position": 1,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Johnson", "ballotGivenName": "Alice"})
    },
    {
        "candidate_name": "Bob Brown",
        "party": "Independent",
        "electorate": "Sydney",
        "ballot_position": 2,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Brown", "ballotGivenName": "Bob"})
    }
]

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for candidate in sample_candidates:
        cursor.execute('''
        INSERT INTO candidates 
        (candidate_name, party, electorate, ballot_position, candidate_type, state, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            candidate["candidate_name"],
            candidate["party"],
            candidate["electorate"],
            candidate["ballot_position"],
            candidate["candidate_type"],
            candidate["state"],
            candidate["data"]
        ))
    
    conn.commit()
    logger.info(f"Successfully inserted {len(sample_candidates)} sample candidates")
    
    cursor.execute("SELECT COUNT(*) FROM candidates")
    count = cursor.fetchone()[0]
    logger.info(f"Total records in candidates table: {count}")
    
    conn.close()
except Exception as e:
    logger.error(f"Error: {e}")
