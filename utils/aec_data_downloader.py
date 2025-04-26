"""
AEC Data Downloader

This utility downloads candidate data from the Australian Electoral Commission (AEC) website
and processes it for use in the Amalfi Results application.
"""

import os
import csv
import json
import logging
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
import sqlite3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

AEC_SENATE_CANDIDATES_URL = "https://aec.gov.au/election/files/data/senate-candidates.csv"
AEC_HOUSE_CANDIDATES_URL = "https://aec.gov.au/election/files/data/house-candidates.csv"

DATA_DIR = Path(__file__).parent.parent / "data"
is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent.parent / "flask_app")
DB_PATH = Path(f"{data_dir_path}/results.db")
logger.info(f"Using database path: {DB_PATH}")


def ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directory ensured at {DATA_DIR}")


def download_file(url: str, output_path: Path) -> bool:
    """
    Download a file from a URL and save it to the specified path.
    
    Args:
        url: URL to download from
        output_path: Path to save the file to
        
    Returns:
        bool: True if download was successful, False otherwise
    """
    try:
        logger.info(f"Downloading {url} to {output_path}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Successfully downloaded {url}")
        return True
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return False


def parse_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """
    Parse a CSV file into a list of dictionaries.
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        List of dictionaries, each representing a row in the CSV
    """
    try:
        logger.info(f"Parsing CSV file: {csv_path}")
        data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(dict(row))
        
        logger.info(f"Successfully parsed {len(data)} rows from {csv_path}")
        return data
    except Exception as e:
        logger.error(f"Error parsing CSV file {csv_path}: {e}")
        return []


def save_to_json(data: List[Dict[str, Any]], output_path: Path) -> bool:
    """
    Save data to a JSON file.
    
    Args:
        data: Data to save
        output_path: Path to save the JSON file to
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        logger.info(f"Saving data to JSON file: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Successfully saved data to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving data to JSON file {output_path}: {e}")
        return False


def create_candidates_table() -> None:
    """Create the candidates table in the SQLite database if it doesn't exist."""
    try:
        logger.info(f"Creating candidates table in database: {DB_PATH}")
        db_path_str = str(DB_PATH)
        logger.info(f"Database path as string: {db_path_str}")
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT NOT NULL,
            party TEXT,
            electorate TEXT NOT NULL,
            ballot_position INTEGER,
            candidate_type TEXT NOT NULL,
            state TEXT,
            data JSON
        )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Successfully created candidates table")
    except Exception as e:
        logger.error(f"Error creating candidates table: {e}")


def save_to_database(candidates: List[Dict[str, Any]], candidate_type: str) -> bool:
    """
    Save candidate data to the SQLite database.
    
    Args:
        candidates: List of candidate dictionaries
        candidate_type: Type of candidates ('senate' or 'house')
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        logger.info(f"Saving {len(candidates)} {candidate_type} candidates to database")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM candidates WHERE candidate_type = ?", (candidate_type,))
        
        for candidate in candidates:
            if candidate == candidates[0]:
                logger.info(f"First candidate data: {candidate}")
            
            if candidate_type == 'senate':
                surname = candidate.get('surname', '')
                given_name = candidate.get('ballotGivenName', '')
                name = f"{given_name} {surname}".strip()
                party = candidate.get('partyBallotName', '')
                electorate = candidate.get('state', '')
                state = candidate.get('state', '')
                try:
                    ballot_position = int(candidate.get('ballotPosition', 0))
                except (ValueError, TypeError):
                    ballot_position = 0
            else:  # house
                surname = candidate.get('surname', '')
                given_name = candidate.get('ballotGivenName', '')
                name = f"{given_name} {surname}".strip()
                party = candidate.get('partyBallotName', '')
                electorate = candidate.get('division', '')
                state = candidate.get('state', '')
                try:
                    ballot_position = int(candidate.get('ballotPosition', 0))
                except (ValueError, TypeError):
                    ballot_position = 0
            
            cursor.execute('''
            INSERT INTO candidates 
            (candidate_name, party, electorate, ballot_position, candidate_type, state, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                name, 
                party, 
                electorate, 
                ballot_position, 
                candidate_type, 
                state, 
                json.dumps(candidate)
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"Successfully saved {candidate_type} candidates to database")
        return True
    except Exception as e:
        logger.error(f"Error saving {candidate_type} candidates to database: {e}")
        return False


def get_candidates_for_electorate(electorate: str) -> List[Dict[str, Any]]:
    """
    Get candidates for a specific electorate from the database.
    
    Args:
        electorate: Name of the electorate
        
    Returns:
        List of candidate dictionaries
    """
    try:
        logger.info(f"Getting candidates for electorate: {electorate}")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM candidates 
        WHERE electorate = ? 
        ORDER BY ballot_position
        ''', (electorate,))
        
        rows = cursor.fetchall()
        candidates = [dict(row) for row in rows]
        
        conn.close()
        logger.info(f"Found {len(candidates)} candidates for electorate {electorate}")
        return candidates
    except Exception as e:
        logger.error(f"Error getting candidates for electorate {electorate}: {e}")
        return []


def download_and_process_aec_data() -> bool:
    """
    Download and process AEC candidate data.
    
    Returns:
        bool: True if all operations were successful, False otherwise
    """
    try:
        ensure_data_dir()
        
        create_candidates_table()
        
        senate_csv_path = DATA_DIR / "senate-candidates.csv"
        if not download_file(AEC_SENATE_CANDIDATES_URL, senate_csv_path):
            return False
        
        house_csv_path = DATA_DIR / "house-candidates.csv"
        if not download_file(AEC_HOUSE_CANDIDATES_URL, house_csv_path):
            return False
        
        senate_candidates = parse_csv(senate_csv_path)
        house_candidates = parse_csv(house_csv_path)
        
        save_to_json(senate_candidates, DATA_DIR / "senate-candidates.json")
        save_to_json(house_candidates, DATA_DIR / "house-candidates.json")
        
        save_to_database(senate_candidates, 'senate')
        save_to_database(house_candidates, 'house')
        
        logger.info("Successfully downloaded and processed AEC candidate data")
        return True
    except Exception as e:
        logger.error(f"Error downloading and processing AEC data: {e}")
        return False


if __name__ == "__main__":
    download_and_process_aec_data()
