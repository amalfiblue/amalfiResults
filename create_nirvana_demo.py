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

def create_booth_results_table():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS booth_results_2022")
        logger.info("Dropped existing booth_results_2022 table")
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS booth_results_2022 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            division_id INTEGER NOT NULL,
            division_name TEXT NOT NULL,
            polling_place_id INTEGER NOT NULL,
            polling_place_name TEXT NOT NULL,
            liberal_national_votes INTEGER,
            liberal_national_percentage REAL,
            labor_votes INTEGER,
            labor_percentage REAL,
            total_votes INTEGER,
            swing REAL,
            data JSON
        )
        ''')
        
        conn.commit()
        logger.info("Successfully created booth_results_2022 table")
        conn.close()
    except Exception as e:
        logger.error(f"Error creating booth_results_2022 table: {e}")

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

def insert_booth_results():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM booth_results_2022 WHERE division_name = 'Nirvana'")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Nirvana booth results already exist ({count} records). Skipping insertion.")
        else:
            for i, booth in enumerate(nirvana_booths):
                total_votes = random.randint(1000, 3000)
                liberal_votes = random.randint(int(total_votes * 0.4), int(total_votes * 0.6))
                labor_votes = total_votes - liberal_votes
                liberal_percent = (liberal_votes / total_votes) * 100
                labor_percent = (labor_votes / total_votes) * 100
                swing = random.uniform(-5.0, 5.0)
                
                data = {
                    "StateAb": "NSW",
                    "DivisionID": 12345,
                    "DivisionNm": "Nirvana",
                    "PollingPlaceID": 10000 + i,
                    "PollingPlace": booth,
                    "Liberal/National Coalition Votes": liberal_votes,
                    "Liberal/National Coalition Percentage": liberal_percent,
                    "Australian Labor Party Votes": labor_votes,
                    "Australian Labor Party Percentage": labor_percent,
                    "TotalVotes": total_votes,
                    "Swing": swing
                }
                
                cursor.execute('''
                INSERT INTO booth_results_2022 
                (state, division_id, division_name, polling_place_id, polling_place_name, 
                liberal_national_votes, liberal_national_percentage, labor_votes, 
                labor_percentage, total_votes, swing, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    "NSW",
                    12345,
                    "Nirvana",
                    10000 + i,
                    booth,
                    liberal_votes,
                    liberal_percent,
                    labor_votes,
                    labor_percent,
                    total_votes,
                    swing,
                    json.dumps(data)
                ))
            
            conn.commit()
            logger.info(f"Successfully inserted {len(nirvana_booths)} Nirvana booth results")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error inserting booth results: {e}")

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
                
                tcp_candidates = random.sample(nirvana_candidates, 2)
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
            tcp_candidates = [nirvana_candidates[0], nirvana_candidates[2]]
            
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
    create_booth_results_table()
    create_results_table()
    insert_candidates()
    insert_booth_results()
    insert_current_results()
    set_tcp_candidates()
    logger.info("Nirvana demo data creation completed")

if __name__ == "__main__":
    create_nirvana_demo()
