"""
Booth Results Processor

This utility processes booth-level results from the 2022 federal election
and provides functionality to calculate swings between historical and current results.
"""

import os
import csv
import json
import logging
import sqlite3
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

AEC_BOOTH_RESULTS_URL = "https://results.aec.gov.au/27966/Website/Downloads/HouseTppByPollingPlaceDownload-27966.csv"

DATA_DIR = Path(__file__).parent.parent / "data"
is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent.parent / "flask_app")
DB_PATH = Path(f"{data_dir_path}/results.db")
logger.info(f"Using database path: {DB_PATH}, exists: {DB_PATH.exists()}")
logger.info(f"Current working directory: {os.getcwd()}")

def ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directory ensured at {DATA_DIR}")
    
def download_booth_results_file() -> bool:
    """
    Download the booth results file from the AEC website.
    
    Returns:
        bool: True if download was successful, False otherwise
    """
    try:
        booth_results_path = DATA_DIR / "HouseTppByPollingPlaceDownload-27966.csv"
        logger.info(f"Downloading booth results file to {booth_results_path}")
        logger.info(f"DATA_DIR: {DATA_DIR}, exists: {DATA_DIR.exists()}, is_dir: {DATA_DIR.is_dir()}")
        logger.info(f"Current working directory: {os.getcwd()}")
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        try:
            response = requests.get(AEC_BOOTH_RESULTS_URL, stream=True)
            response.raise_for_status()
            
            with open(booth_results_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Successfully downloaded booth results file to {booth_results_path}")
            logger.info(f"File exists: {booth_results_path.exists()}, size: {booth_results_path.stat().st_size if booth_results_path.exists() else 0} bytes")
            return True
        except requests.exceptions.RequestException as re:
            logger.error(f"Request error downloading booth results file: {re}")
            return False
    except Exception as e:
        logger.error(f"Error downloading booth results file: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def create_booth_results_table() -> None:
    """Create the booth_results table in the SQLite database if it doesn't exist."""
    try:
        logger.info(f"Creating booth_results table in database: {DB_PATH}")
        db_path_str = str(DB_PATH)
        logger.info(f"Database path as string: {db_path_str}")
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
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
        conn.close()
        logger.info("Successfully created booth_results_2022 table")
    except Exception as e:
        logger.error(f"Error creating booth_results_2022 table: {e}")

def process_booth_results_file(file_path: Path) -> List[Dict[str, Any]]:
    """
    Process the booth results CSV file.
    
    Args:
        file_path: Path to the CSV file
        
    Returns:
        List of dictionaries, each representing a row in the CSV
    """
    try:
        logger.info(f"Processing booth results file: {file_path}")
        results = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            next(f)
            reader = csv.DictReader(f)
            
            for row in reader:
                processed_row = {
                    'state': row.get('StateAb', ''),
                    'division_id': int(row.get('DivisionID', 0)),
                    'division_name': row.get('DivisionNm', ''),
                    'polling_place_id': int(row.get('PollingPlaceID', 0)),
                    'polling_place_name': row.get('PollingPlace', ''),
                    'liberal_national_votes': int(row.get('Liberal/National Coalition Votes', 0)),
                    'liberal_national_percentage': float(row.get('Liberal/National Coalition Percentage', 0)),
                    'labor_votes': int(row.get('Australian Labor Party Votes', 0)),
                    'labor_percentage': float(row.get('Australian Labor Party Percentage', 0)),
                    'total_votes': int(row.get('TotalVotes', 0)),
                    'swing': float(row.get('Swing', 0)),
                    'data': json.dumps(row)
                }
                results.append(processed_row)
        
        logger.info(f"Successfully processed {len(results)} booth results")
        return results
    except Exception as e:
        logger.error(f"Error processing booth results file {file_path}: {e}")
        return []

def save_booth_results_to_database(results: List[Dict[str, Any]]) -> bool:
    """
    Save booth results to the SQLite database.
    
    Args:
        results: List of booth result dictionaries
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        logger.info(f"Saving {len(results)} booth results to database")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM booth_results_2022")
        
        for result in results:
            cursor.execute('''
            INSERT INTO booth_results_2022 
            (state, division_id, division_name, polling_place_id, polling_place_name, 
             liberal_national_votes, liberal_national_percentage, labor_votes, 
             labor_percentage, total_votes, swing, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result['state'],
                result['division_id'],
                result['division_name'],
                result['polling_place_id'],
                result['polling_place_name'],
                result['liberal_national_votes'],
                result['liberal_national_percentage'],
                result['labor_votes'],
                result['labor_percentage'],
                result['total_votes'],
                result['swing'],
                result['data']
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"Successfully saved booth results to database")
        return True
    except Exception as e:
        logger.error(f"Error saving booth results to database: {e}")
        return False

def get_booth_results_for_division(division_name: str) -> List[Dict[str, Any]]:
    """
    Get booth results for a specific division from the database.
    
    Args:
        division_name: Name of the division/electorate
        
    Returns:
        List of booth result dictionaries
    """
    try:
        logger.info(f"Getting booth results for division: {division_name}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM booth_results_2022 
        WHERE division_name = ? 
        ORDER BY polling_place_name
        ''', (division_name,))
        
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        
        # Get TCP candidates for this division
        tcp_candidates = get_tcp_candidates_for_division(division_name)
        
        for result in results:
            result['tcp_candidates'] = tcp_candidates
            
            if len(tcp_candidates) >= 2:
                try:
                    raw_data = json.loads(result.get('data', '{}'))
                    
                    # Find the TCP percentages for the actual candidates
                    tcp_candidate_1 = tcp_candidates[0]['candidate_name']
                    tcp_candidate_1_party = tcp_candidates[0]['party']
                    tcp_candidate_2 = tcp_candidates[1]['candidate_name']
                    tcp_candidate_2_party = tcp_candidates[1]['party']
                    
                    logger.info(f"Raw data keys for polling place: {result.get('polling_place_name', 'Unknown')}")
                    logger.info(f"TCP candidates: {tcp_candidate_1} ({tcp_candidate_1_party}) and {tcp_candidate_2} ({tcp_candidate_2_party})")
                    logger.info(f"Raw data keys: {list(raw_data.keys())}")
                    
                    # For Liberal/National candidates
                    if tcp_candidate_1_party in ['LIB', 'NAT', 'LNP']:
                        tcp_candidate_1_votes = int(raw_data.get("Liberal/National Coalition Votes", 0))
                        tcp_candidate_1_percentage = float(raw_data.get("Liberal/National Coalition Percentage", 0))
                    # For Labor candidates
                    elif tcp_candidate_1_party == 'ALP':
                        tcp_candidate_1_votes = int(raw_data.get("Australian Labor Party Votes", 0))
                        tcp_candidate_1_percentage = float(raw_data.get("Australian Labor Party Percentage", 0))
                    # For independent candidates - use 100% minus the other candidate's percentage
                    else:
                        # We need to calculate Andrew Wilkie's percentage as 100% - Simon Behrakis's percentage
                        
                        if tcp_candidate_2_party in ['LIB', 'NAT', 'LNP']:
                            lib_percentage = float(raw_data.get("Liberal/National Coalition Percentage", 0))
                            # Calculate independent percentage as 100% - Liberal percentage
                            tcp_candidate_1_percentage = 100.0 - lib_percentage
                            tcp_candidate_1_votes = int(raw_data.get("TotalVotes", 0)) - int(raw_data.get("Liberal/National Coalition Votes", 0))
                        elif tcp_candidate_2_party == 'ALP':
                            alp_percentage = float(raw_data.get("Australian Labor Party Percentage", 0))
                            # Calculate independent percentage as 100% - Labor percentage
                            tcp_candidate_1_percentage = 100.0 - alp_percentage
                            tcp_candidate_1_votes = int(raw_data.get("TotalVotes", 0)) - int(raw_data.get("Australian Labor Party Votes", 0))
                        else:
                            tcp_candidate_1_votes = 0
                            tcp_candidate_1_percentage = 0
                    
                    if tcp_candidate_2_party in ['LIB', 'NAT', 'LNP']:
                        tcp_candidate_2_votes = int(raw_data.get("Liberal/National Coalition Votes", 0))
                        tcp_candidate_2_percentage = float(raw_data.get("Liberal/National Coalition Percentage", 0))
                    elif tcp_candidate_2_party == 'ALP':
                        tcp_candidate_2_votes = int(raw_data.get("Australian Labor Party Votes", 0))
                        tcp_candidate_2_percentage = float(raw_data.get("Australian Labor Party Percentage", 0))
                    else:
                        # For independent candidates - use 100% minus the other candidate's percentage
                        if tcp_candidate_1_party in ['LIB', 'NAT', 'LNP']:
                            lib_percentage = float(raw_data.get("Liberal/National Coalition Percentage", 0))
                            # Calculate independent percentage as 100% - Liberal percentage
                            tcp_candidate_2_percentage = 100.0 - lib_percentage
                            tcp_candidate_2_votes = int(raw_data.get("TotalVotes", 0)) - int(raw_data.get("Liberal/National Coalition Votes", 0))
                        elif tcp_candidate_1_party == 'ALP':
                            alp_percentage = float(raw_data.get("Australian Labor Party Percentage", 0))
                            # Calculate independent percentage as 100% - Labor percentage
                            tcp_candidate_2_percentage = 100.0 - alp_percentage
                            tcp_candidate_2_votes = int(raw_data.get("TotalVotes", 0)) - int(raw_data.get("Australian Labor Party Votes", 0))
                        else:
                            tcp_candidate_2_votes = 0
                            tcp_candidate_2_percentage = 0
                    
                    result['tcp_candidate_1_name'] = tcp_candidate_1
                    result['tcp_candidate_1_party'] = tcp_candidates[0]['party']
                    result['tcp_candidate_1_votes'] = tcp_candidate_1_votes
                    result['tcp_candidate_1_percentage'] = tcp_candidate_1_percentage
                    
                    result['tcp_candidate_2_name'] = tcp_candidate_2
                    result['tcp_candidate_2_party'] = tcp_candidates[1]['party']
                    result['tcp_candidate_2_votes'] = tcp_candidate_2_votes
                    result['tcp_candidate_2_percentage'] = tcp_candidate_2_percentage
                    
                    # Calculate swing based on TCP candidates
                    if tcp_candidate_1_percentage and tcp_candidate_2_percentage:
                        result['tcp_swing'] = tcp_candidate_1_percentage - tcp_candidate_2_percentage
                    else:
                        result['tcp_swing'] = 0
                        
                except Exception as e:
                    logger.error(f"Error processing TCP data for polling place: {e}")
                    pass
        
        conn.close()
        logger.info(f"Found {len(results)} booth results for division {division_name}")
        return results
    except Exception as e:
        logger.error(f"Error getting booth results for division {division_name}: {e}")
        return []

def get_booth_results_for_polling_place(division_name: str, polling_place_name: str) -> Optional[Dict[str, Any]]:
    """
    Get booth results for a specific polling place in a division from the database.
    
    Args:
        division_name: Name of the division/electorate
        polling_place_name: Name of the polling place/booth
        
    Returns:
        Booth result dictionary or None if not found
    """
    try:
        logger.info(f"Getting booth results for polling place: {polling_place_name} in division: {division_name}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM booth_results_2022 
        WHERE division_name = ? AND polling_place_name = ?
        ''', (division_name, polling_place_name))
        
        row = cursor.fetchone()
        
        if row is None:
            cursor.execute('''
            SELECT * FROM booth_results_2022 
            WHERE division_name = ? AND polling_place_name LIKE ?
            ''', (division_name, f"%{polling_place_name}%"))
            
            row = cursor.fetchone()
        
        result = dict(row) if row else None
        
        conn.close()
        if result:
            logger.info(f"Found booth results for polling place {polling_place_name} in division {division_name}")
        else:
            logger.info(f"No booth results found for polling place {polling_place_name} in division {division_name}")
        
        return result
    except Exception as e:
        logger.error(f"Error getting booth results for polling place {polling_place_name} in division {division_name}: {e}")
        return None

def get_tcp_candidates_for_division(division_name: str) -> List[Dict[str, Any]]:
    """
    Get TCP candidates for a specific division from the database.
    
    Args:
        division_name: Name of the division/electorate
        
    Returns:
        List of TCP candidate dictionaries
    """
    try:
        logger.info(f"Getting TCP candidates for division: {division_name}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM tcp_candidates 
        WHERE electorate = ? 
        ORDER BY id
        ''', (division_name,))
        
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        
        conn.close()
        logger.info(f"Found {len(results)} TCP candidates for division {division_name}")
        return results
    except Exception as e:
        logger.error(f"Error getting TCP candidates for division {division_name}: {e}")
        return []

def calculate_swing(current_result: Dict[str, Any], historical_result: Dict[str, Any]) -> float:
    """
    Calculate the swing between current and historical results.
    
    Args:
        current_result: Current election result
        historical_result: Historical (2022) election result
        
    Returns:
        float: Calculated swing percentage
    """
    try:
        current_liberal_pct = current_result.get('liberal_national_percentage', 0)
        current_labor_pct = current_result.get('labor_percentage', 0)
        
        historical_liberal_pct = historical_result.get('liberal_national_percentage', 0)
        historical_labor_pct = historical_result.get('labor_percentage', 0)
        
        swing = (current_labor_pct - historical_labor_pct)
        
        return round(swing, 2)
    except Exception as e:
        logger.error(f"Error calculating swing: {e}")
        return 0.0

def process_and_load_booth_results() -> bool:
    """
    Process and load booth results from the 2022 federal election.
    Downloads the booth results file if it doesn't exist.
    
    Returns:
        bool: True if all operations were successful, False otherwise
    """
    try:
        ensure_data_dir()
        
        create_booth_results_table()
        
        booth_results_path = DATA_DIR / "HouseTppByPollingPlaceDownload-27966.csv"
        if not booth_results_path.exists():
            logger.info(f"Booth results file not found at {booth_results_path}, downloading...")
            if not download_booth_results_file():
                logger.error("Failed to download booth results file")
                return False
        
        if not booth_results_path.exists():
            logger.error(f"Booth results file still not found at {booth_results_path} after download attempt")
            return False
            
        logger.info(f"Processing booth results file: {booth_results_path}")
        results = process_booth_results_file(booth_results_path)
        if not results:
            logger.error("Failed to process booth results file")
            return False
        
        logger.info(f"Saving {len(results)} booth results to database")
        success = save_booth_results_to_database(results)
        
        if success:
            logger.info("Successfully processed and loaded booth results")
        else:
            logger.error("Failed to save booth results to database")
            
        return success
    except Exception as e:
        logger.error(f"Error processing and loading booth results: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    process_and_load_booth_results()
