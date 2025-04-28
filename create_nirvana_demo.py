import sqlite3
import os
import logging
import json
import random

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else "./data"
db_path = f"{data_dir_path}/results.db"

logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Using database path: {db_path}")
logger.info(f"Database file exists: {os.path.exists(db_path)}")

os.makedirs(data_dir_path, exist_ok=True)

nirvana_candidates = [
    {
        "candidate_name": "Mickey Mouse",
        "party": "Cartoon Party",
        "electorate": "Nirvana",
        "ballot_position": 1,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Mouse", "ballotGivenName": "Mickey"})
    },
    {
        "candidate_name": "Donald Duck",
        "party": "Cartoon Party",
        "electorate": "Nirvana",
        "ballot_position": 2,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Duck", "ballotGivenName": "Donald"})
    },
    {
        "candidate_name": "Bugs Bunny",
        "party": "Looney Party",
        "electorate": "Nirvana",
        "ballot_position": 3,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Bunny", "ballotGivenName": "Bugs"})
    },
    {
        "candidate_name": "Daffy Duck",
        "party": "Looney Party",
        "electorate": "Nirvana",
        "ballot_position": 4,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Duck", "ballotGivenName": "Daffy"})
    },
    {
        "candidate_name": "Homer Simpson",
        "party": "Springfield Party",
        "electorate": "Nirvana",
        "ballot_position": 5,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Simpson", "ballotGivenName": "Homer"})
    },
    {
        "candidate_name": "SpongeBob SquarePants",
        "party": "Bikini Bottom Party",
        "electorate": "Nirvana",
        "ballot_position": 6,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "SquarePants", "ballotGivenName": "SpongeBob"})
    },
    {
        "candidate_name": "Scooby Doo",
        "party": "Mystery Party",
        "electorate": "Nirvana",
        "ballot_position": 7,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Doo", "ballotGivenName": "Scooby"})
    },
    {
        "candidate_name": "Fred Flintstone",
        "party": "Stone Age Party",
        "electorate": "Nirvana",
        "ballot_position": 8,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Flintstone", "ballotGivenName": "Fred"})
    },
    {
        "candidate_name": "Popeye",
        "party": "Sailors Party",
        "electorate": "Nirvana",
        "ballot_position": 9,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Popeye", "ballotGivenName": ""})
    },
    {
        "candidate_name": "Bart Simpson",
        "party": "Springfield Party",
        "electorate": "Nirvana",
        "ballot_position": 10,
        "candidate_type": "house",
        "state": "NSW",
        "data": json.dumps({"surname": "Simpson", "ballotGivenName": "Bart"})
    }
]

nirvana_booths = [
    "Cartoon Central",
    "Animation Station",
    "Toontown Hall",
    "Fantasy Fields",
    "Comic Corner"
]

def create_candidates_table():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT NOT NULL,
            party TEXT,
            electorate TEXT,
            ballot_position INTEGER,
            candidate_type TEXT,
            state TEXT,
            data TEXT
        )
        ''')
        
        conn.commit()
        logger.info("Successfully created candidates table")
        conn.close()
    except Exception as e:
        logger.error(f"Error creating candidates table: {e}")

def create_polling_places_table():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS polling_places")
        logger.info("Dropped existing polling_places table")
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS polling_places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            division_id INTEGER NOT NULL,
            division_name TEXT NOT NULL,
            polling_place_id INTEGER NOT NULL,
            polling_place_name TEXT NOT NULL,
            address TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT,
            wheelchair_access TEXT,
            data JSON
        )
        ''')
        
        conn.commit()
        logger.info("Successfully created polling_places table")
        conn.close()
    except Exception as e:
        logger.error(f"Error creating polling_places table: {e}")

def create_results_table():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            electorate TEXT,
            booth_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            image_url TEXT,
            is_reviewed BOOLEAN DEFAULT 0,
            reviewer TEXT,
            data TEXT
        )
        ''')
        
        conn.commit()
        logger.info("Successfully created results table")
        conn.close()
    except Exception as e:
        logger.error(f"Error creating results table: {e}")

def insert_candidates():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM candidates WHERE electorate = 'Nirvana'")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Nirvana candidates already exist ({count} records). Skipping insertion.")
        else:
            for candidate in nirvana_candidates:
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
            logger.info(f"Successfully inserted {len(nirvana_candidates)} Nirvana candidates")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error inserting candidates: {e}")

def insert_polling_places():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places WHERE division_name = 'Nirvana'")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Nirvana polling places already exist ({count} records). Skipping insertion.")
        else:
            for i, booth in enumerate(nirvana_booths):
                polling_place_id = 10000 + i
                
                data = {
                    "state": "NSW",
                    "division_id": 12345,
                    "division_name": "Nirvana",
                    "polling_place_id": polling_place_id,
                    "polling_place_name": booth
                }
                
                cursor.execute('''
                INSERT INTO polling_places 
                (state, division_id, division_name, polling_place_id, polling_place_name, 
                address, status, wheelchair_access, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    "NSW",
                    12345,
                    "Nirvana",
                    polling_place_id,
                    booth,
                    f"{booth} Polling Place, Nirvana, NSW",
                    "Current",
                    "Yes" if random.random() > 0.2 else "No",
                    json.dumps(data)
                ))
            
            conn.commit()
            logger.info(f"Successfully inserted {len(nirvana_booths)} Nirvana polling places")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error inserting polling places: {e}")

def insert_current_results():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM results WHERE electorate = 'Nirvana'")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Nirvana results already exist ({count} records). Skipping insertion.")
        else:
            for booth in nirvana_booths:
                votes = {}
                total_votes = random.randint(1000, 3000)
                remaining_votes = total_votes
                
                for i, candidate in enumerate(nirvana_candidates):
                    if i == len(nirvana_candidates) - 1:
                        votes[candidate["candidate_name"]] = remaining_votes
                    else:
                        candidate_votes = random.randint(50, min(500, remaining_votes - 50 * (len(nirvana_candidates) - i - 1)))
                        votes[candidate["candidate_name"]] = candidate_votes
                        remaining_votes -= candidate_votes
                
                # Use Mickey Mouse and Donald Duck as TCP candidates
                tcp_candidates = [nirvana_candidates[0], nirvana_candidates[1]]  # Mickey and Donald
                tcp_votes = {}
                tcp_total = total_votes
                tcp_votes[tcp_candidates[0]["candidate_name"]] = random.randint(int(tcp_total * 0.4), int(tcp_total * 0.6))
                tcp_votes[tcp_candidates[1]["candidate_name"]] = tcp_total - tcp_votes[tcp_candidates[0]["candidate_name"]]
                
                result_data = {
                    "primary_votes": votes,
                    "tcp_votes": tcp_votes,
                    "totals": {
                        "formal": total_votes,
                        "informal": random.randint(50, 200),
                        "total": total_votes + random.randint(50, 200)
                    }
                }
                
                cursor.execute('''
                INSERT INTO results 
                (electorate, booth_name, timestamp, image_url, is_reviewed, reviewer, data)
                VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
                ''', (
                    "Nirvana",
                    booth,
                    None,  # image_url
                    True,  # is_reviewed
                    "Demo Creator",  # reviewer
                    json.dumps(result_data)
                ))
            
            conn.commit()
            logger.info(f"Successfully inserted {len(nirvana_booths)} Nirvana current results")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error inserting current results: {e}")

def set_tcp_candidates():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tcp_candidates'")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            cursor.execute('''
            CREATE TABLE tcp_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                electorate TEXT NOT NULL,
                candidate_name TEXT NOT NULL,
                party TEXT,
                UNIQUE(electorate, candidate_name)
            )
            ''')
            logger.info("Created tcp_candidates table")
        
        cursor.execute("SELECT COUNT(*) FROM tcp_candidates WHERE electorate = 'Nirvana'")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Nirvana TCP candidates already exist ({count} records). Skipping insertion.")
        else:
            tcp_candidates = [nirvana_candidates[0], nirvana_candidates[1]]  # Mickey Mouse and Donald Duck
            
            for candidate in tcp_candidates:
                cursor.execute('''
                INSERT INTO tcp_candidates 
                (electorate, candidate_name, party)
                VALUES (?, ?, ?)
                ''', (
                    "Nirvana",
                    candidate["candidate_name"],
                    candidate["party"]
                ))
            
            conn.commit()
            logger.info(f"Successfully set {len(tcp_candidates)} Nirvana TCP candidates")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error setting TCP candidates: {e}")

def create_nirvana_demo():
    create_candidates_table()
    create_polling_places_table()
    create_results_table()
    insert_candidates()
    insert_polling_places()
    insert_current_results()
    set_tcp_candidates()
    logger.info("Nirvana demo data creation completed")

if __name__ == "__main__":
    create_nirvana_demo()
