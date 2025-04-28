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

def get_polling_place_by_id(polling_place_id: int) -> Optional[Dict[str, Any]]:
    """
    Get polling place by ID from the polling_places table.
    
    Args:
        polling_place_id: ID of the polling place
        
    Returns:
        Polling place dictionary or None if not found
    """
    try:
        logger.info(f"Getting polling place by ID: {polling_place_id}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM polling_places 
        WHERE polling_place_id = ?
        ''', (polling_place_id,))
        
        row = cursor.fetchone()
        result = dict(row) if row else None
        
        conn.close()
        if result:
            logger.info(f"Found polling place with ID {polling_place_id}")
        else:
            logger.info(f"No polling place found with ID {polling_place_id}")
        
        return result
    except Exception as e:
        logger.error(f"Error getting polling place by ID {polling_place_id}: {e}")
        return None

def get_booth_result_by_polling_place_id(polling_place_id: int) -> Optional[Dict[str, Any]]:
    """
    Get 2022 booth result by polling place ID.
    
    Args:
        polling_place_id: ID of the polling place
        
    Returns:
        Booth result dictionary or None if not found
    """
    try:
        logger.info(f"Getting 2022 booth result for polling place ID: {polling_place_id}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM booth_results_2022 
        WHERE polling_place_id = ?
        ''', (polling_place_id,))
        
        row = cursor.fetchone()
        result = dict(row) if row else None
        
        conn.close()
        if result:
            logger.info(f"Found 2022 booth result for polling place ID {polling_place_id}")
        else:
            logger.info(f"No 2022 booth result found for polling place ID {polling_place_id}")
        
        return result
    except Exception as e:
        logger.error(f"Error getting 2022 booth result for polling place ID {polling_place_id}: {e}")
        return None

def create_polling_places_table() -> None:
    """Create the polling_places table in the SQLite database if it doesn't exist."""
    try:
        logger.info(f"Creating polling_places table in database: {DB_PATH}")
        db_path_str = str(DB_PATH)
        logger.info(f"Database path as string: {db_path_str}")
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(polling_places)")
        columns = {column[1] for column in cursor.fetchall()}
        
        required_columns = {'status', 'wheelchair_access', 'address', 'latitude', 'longitude'}
        missing_columns = required_columns - columns
        
        if columns and missing_columns:
            logger.info(f"Polling places table exists but is missing columns: {missing_columns}")
            logger.info("Dropping and recreating polling_places table with correct schema")
            cursor.execute("DROP TABLE polling_places")
            conn.commit()
        
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
        conn.close()
        logger.info("Successfully created polling_places table")
    except Exception as e:
        logger.error(f"Error creating polling_places table: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

def download_polling_places_data() -> bool:
    """
    Download polling places data from AEC for the current election.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Attempting to download polling places data from AEC")
        
        polling_places_dir = DATA_DIR / "polling_places"
        polling_places_dir.mkdir(exist_ok=True)
        
        # This is the actual URL from the AEC website for the 2025 federal election
        polling_places_url = "https://www.aec.gov.au/About_AEC/cea-notices/files/prdelms-gaz-statics.csv"
        polling_places_path = polling_places_dir / "polling-places-2025.csv"
        
        if polling_places_path.exists():
            logger.info(f"Polling places file already exists at {polling_places_path}")
            return True
            
        try:
            logger.info(f"Downloading polling places data from {polling_places_url}")
            response = requests.get(polling_places_url, timeout=30)
            response.raise_for_status()
            
            with open(polling_places_path, 'wb') as f:
                f.write(response.content)
                
            logger.info(f"Successfully downloaded polling places data to {polling_places_path}")
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not download polling places data from AEC website: {e}")
            logger.warning("Checking for local copy of the polling places data...")
            
            possible_paths = [
                Path("~/browser_downloads/prdelms.gaz.statics.250428.09.00.02.csv").expanduser(),
                Path("/home/ubuntu/browser_downloads/prdelms.gaz.statics.250428.09.00.02.csv"),
                Path("/tmp/prdelms.gaz.statics.250428.09.00.02.csv")
            ]
            
            for local_copy in possible_paths:
                if local_copy.exists():
                    logger.info(f"Found local copy of polling places data at {local_copy}")
                    import shutil
                    shutil.copy(local_copy, polling_places_path)
                    logger.info(f"Copied local polling places data to {polling_places_path}")
                    return True
            
            logger.info(f"Checked these paths for local polling places data: {possible_paths}")
            logger.info(f"None of the local paths exist")
            logger.warning("No local copy found. Falling back to extracting polling places from 2022 booth results")
            return False
    except Exception as e:
        logger.error(f"Error downloading polling places data: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def process_polling_places_file(file_path: Path) -> List[Dict[str, Any]]:
    """
    Process the polling places CSV file into structured data.
    
    Args:
        file_path: Path to the polling places CSV file
        
    Returns:
        List of polling place dictionaries
    """
    try:
        logger.info(f"Processing polling places file: {file_path}")
        
        if not file_path.exists():
            logger.error(f"Polling places file not found at {file_path}")
            return []
            
        polling_places = []
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            import csv
            reader = csv.DictReader(f)
            
            headers = reader.fieldnames
            logger.info(f"CSV headers: {headers}")
            
            valid_count = 0
            skipped_count = 0
            
            for row in reader:
                try:
                    if row.get('Status') == 'Abolition':
                        skipped_count += 1
                        continue
                    
                    if not row.get('PPId') or not row.get('DivName'):
                        skipped_count += 1
                        continue
                        
                    division_name = row.get('DivName', '').strip()
                    
                    polling_place_name = row.get('PPName', '').strip()
                    if ' (' in polling_place_name:
                        polling_place_name = polling_place_name.split(' (')[0].strip()
                    
                    address_parts = []
                    if row.get('PremisesName'):
                        address_parts.append(row.get('PremisesName').strip())
                    if row.get('Address1'):
                        address_parts.append(row.get('Address1').strip())
                    if row.get('Address2') and row.get('Address2').strip():
                        address_parts.append(row.get('Address2').strip())
                    if row.get('Address3') and row.get('Address3').strip():
                        address_parts.append(row.get('Address3').strip())
                    if row.get('Locality'):
                        address_parts.append(row.get('Locality').strip())
                    if row.get('AddrStateAb'):
                        address_parts.append(row.get('AddrStateAb').strip())
                    if row.get('Postcode'):
                        address_parts.append(row.get('Postcode').strip())
                    
                    address = ", ".join([part for part in address_parts if part and part.strip()])
                    
                    try:
                        polling_place_id = int(row.get('PPId', 0))
                        if polling_place_id <= 0:
                            logger.warning(f"Invalid polling place ID: {polling_place_id}, skipping row")
                            skipped_count += 1
                            continue
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid polling place ID format: {row.get('PPId')}, skipping row")
                        skipped_count += 1
                        continue
                        
                    try:
                        division_id = int(row.get('DivId', 0))
                    except (ValueError, TypeError):
                        division_id = 0
                        
                    try:
                        latitude = float(row.get('Lat', 0)) if row.get('Lat') and row.get('Lat').strip() else None
                    except (ValueError, TypeError):
                        latitude = None
                        
                    try:
                        longitude = float(row.get('Long', 0)) if row.get('Long') and row.get('Long').strip() else None
                    except (ValueError, TypeError):
                        longitude = None
                    
                    place = {
                        'state': row.get('StateAb', '').strip(),
                        'division_id': division_id,
                        'division_name': division_name,
                        'polling_place_id': polling_place_id,
                        'polling_place_name': polling_place_name,
                        'address': address,
                        'latitude': latitude,
                        'longitude': longitude,
                        'status': row.get('Status', '').strip(),
                        'wheelchair_access': row.get('WheelchairAccess', '').strip()
                    }
                    
                    if not place['state'] or not place['division_name'] or not place['polling_place_name']:
                        logger.warning(f"Missing required fields in row, skipping: {place}")
                        skipped_count += 1
                        continue
                    
                    if ('North Sydney' in polling_place_name or 
                        'Cammeray' in polling_place_name or 
                        'Wollstonecraft' in polling_place_name):
                        logger.info(f"North Sydney area booth in CSV: {polling_place_id} | {polling_place_name} | Division: {division_name} | Row data: {row}")
                    
                    polling_places.append(place)
                    valid_count += 1
                    
                    if valid_count % 100 == 0:
                        logger.info(f"Processed {valid_count} valid polling places so far")
                        
                except Exception as e:
                    logger.warning(f"Error processing row: {row}, error: {e}")
                    skipped_count += 1
                    continue
                    
        logger.info(f"Processed {len(polling_places)} valid polling places from file (skipped {skipped_count})")
        
        if polling_places:
            logger.info(f"Sample polling place: {polling_places[0]}")
            
        return polling_places
    except Exception as e:
        logger.error(f"Error processing polling places file: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []

def save_polling_places_to_database(polling_places: List[Dict[str, Any]]) -> bool:
    """
    Save polling places to the database.
    
    Args:
        polling_places: List of polling place dictionaries
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not polling_places:
            logger.warning("No polling places to save to database")
            return False
            
        logger.info(f"Saving {len(polling_places)} polling places to database")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
        # First, completely clear the polling_places table
        cursor.execute("DELETE FROM polling_places")
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        count = cursor.fetchone()[0]
        logger.info(f"Polling places table has {count} records after clearing")
        
        valid_polling_places = []
        invalid_count = 0
        
        for place in polling_places:
            if (not place.get('state') or 
                not place.get('division_name') or 
                not place.get('polling_place_name') or 
                place.get('polling_place_id', 0) <= 0 or 
                place.get('division_id', 0) <= 0):
                invalid_count += 1
                continue
                
            valid_polling_places.append(place)
        
        logger.info(f"Filtered out {invalid_count} invalid records, proceeding with {len(valid_polling_places)} valid records")
        
        for place in valid_polling_places:
            cursor.execute('''
            INSERT INTO polling_places
            (state, division_id, division_name, polling_place_id, polling_place_name, 
             address, latitude, longitude, status, wheelchair_access, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                place['state'],
                place['division_id'],
                place['division_name'],
                place['polling_place_id'],
                place['polling_place_name'],
                place.get('address', ''),
                place.get('latitude'),
                place.get('longitude'),
                place.get('status', 'Current'),
                place.get('wheelchair_access', ''),
                json.dumps(place)
            ))
        
        conn.commit()
        
        cursor.execute("""
        SELECT COUNT(*) FROM polling_places 
        WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
              division_name = '' OR polling_place_name = ''
        """)
        empty_count = cursor.fetchone()[0]
        
        if empty_count > 0:
            logger.warning(f"Found {empty_count} empty records after insertion, removing them")
            cursor.execute("""
            DELETE FROM polling_places 
            WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
                  division_name = '' OR polling_place_name = ''
            """)
            conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        final_count = cursor.fetchone()[0]
        logger.info(f"Successfully saved {final_count} polling places to database")
        
        conn.close()
        return final_count > 0
    except Exception as e:
        logger.error(f"Error saving polling places to database: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def extract_and_save_polling_places() -> bool:
    """
    Extract polling place data from booth_results_2022 and save to polling_places table.
    This is a fallback method when current polling places data is not available.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Extracting polling places from booth_results_2022 as fallback")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # First, completely clear the polling_places table
        cursor.execute("DELETE FROM polling_places")
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        count = cursor.fetchone()[0]
        logger.info(f"Polling places table has {count} records after clearing")
        
        # Get unique polling places from booth_results_2022
        cursor.execute('''
        SELECT DISTINCT 
            state, 
            division_id, 
            division_name, 
            polling_place_id, 
            polling_place_name
        FROM booth_results_2022
        WHERE state != '' AND division_id > 0 AND polling_place_id > 0 
        AND division_name != '' AND polling_place_name != ''
        ORDER BY division_name, polling_place_name
        ''')
        
        polling_places = [dict(row) for row in cursor.fetchall()]
        logger.info(f"Found {len(polling_places)} unique valid polling places from 2022 data")
        
        valid_polling_places = []
        invalid_count = 0
        
        for place in polling_places:
            if (not place.get('state') or 
                not place.get('division_name') or 
                not place.get('polling_place_name') or 
                place.get('polling_place_id', 0) <= 0 or 
                place.get('division_id', 0) <= 0):
                invalid_count += 1
                continue
                
            place['status'] = 'Current'
            place['wheelchair_access'] = ''
            valid_polling_places.append(place)
        
        logger.info(f"Filtered out {invalid_count} invalid records, proceeding with {len(valid_polling_places)} valid records")
        
        for place in valid_polling_places:
            cursor.execute('''
            INSERT INTO polling_places
            (state, division_id, division_name, polling_place_id, polling_place_name, 
             status, wheelchair_access, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                place['state'],
                place['division_id'],
                place['division_name'],
                place['polling_place_id'],
                place['polling_place_name'],
                place['status'],
                place['wheelchair_access'],
                json.dumps(place)
            ))
        
        conn.commit()
        
        cursor.execute("""
        SELECT COUNT(*) FROM polling_places 
        WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
              division_name = '' OR polling_place_name = ''
        """)
        empty_count = cursor.fetchone()[0]
        
        if empty_count > 0:
            logger.warning(f"Found {empty_count} empty records after insertion, removing them")
            cursor.execute("""
            DELETE FROM polling_places 
            WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
                  division_name = '' OR polling_place_name = ''
            """)
            conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        final_count = cursor.fetchone()[0]
        logger.info(f"Successfully saved {final_count} polling places to database (from 2022 data)")
        
        conn.close()
        return final_count > 0
    except Exception as e:
        logger.error(f"Error extracting and saving polling places: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def get_polling_places_for_division(division_name: str, include_comparison: bool = False) -> List[Dict[str, Any]]:
    """
    Get polling places for a specific division from the database.
    
    Args:
        division_name: Name of the division/electorate
        include_comparison: Whether to include comparison with 2022 results
        
    Returns:
        List of polling place dictionaries
    """
    try:
        logger.info(f"Getting polling places for division: {division_name}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM polling_places 
        WHERE division_name = ? 
        ORDER BY polling_place_name
        ''', (division_name,))
        
        rows = cursor.fetchall()
        polling_places = [dict(row) for row in rows]
        
        # If comparison is requested, add 2022 booth results for each polling place
        if include_comparison:
            for place in polling_places:
                polling_place_id = place.get('polling_place_id')
                if polling_place_id:
                    # Get 2022 booth result for this polling place ID
                    booth_result = get_booth_result_by_polling_place_id(polling_place_id)
                    if booth_result:
                        place['booth_result_2022'] = booth_result
                        place['has_2022_comparison'] = True
                        place['comparison_type'] = 'direct'
                        place['original_division_2022'] = booth_result.get('division_name')
                    else:
                        if division_name == 'Warringah':
                            cursor.execute('''
                            SELECT * FROM booth_results_2022 
                            WHERE polling_place_id = ? AND division_name = 'North Sydney'
                            ''', (polling_place_id,))
                            
                            north_sydney_row = cursor.fetchone()
                            if north_sydney_row:
                                north_sydney_result = dict(north_sydney_row)
                                place['booth_result_2022'] = north_sydney_result
                                place['has_2022_comparison'] = True
                                place['comparison_type'] = 'redistribution'
                                place['original_division_2022'] = 'North Sydney'
                                
                                # Get TCP candidates for North Sydney
                                tcp_candidates = get_tcp_candidates_for_division('North Sydney')
                                if tcp_candidates:
                                    place['tcp_candidates_2022'] = tcp_candidates
                            else:
                                place['has_2022_comparison'] = False
                        else:
                            place['has_2022_comparison'] = False
                else:
                    place['has_2022_comparison'] = False
        
        conn.close()
        logger.info(f"Found {len(polling_places)} polling places for division {division_name}")
        return polling_places
    except Exception as e:
        logger.error(f"Error getting polling places for division {division_name}: {e}")
        try:
            logger.info(f"Falling back to booth_results_2022 for division: {division_name}")
            return get_booth_results_for_division(division_name)
        except Exception as fallback_e:
            logger.error(f"Error in fallback: {fallback_e}")
            return []

def process_and_load_polling_places() -> bool:
    """
    Process and load polling places data.
    Loads ONLY 2025 polling places data from AEC.
    NO fallback to 2022 data.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ensure_data_dir()
        create_polling_places_table()
        
        # First, completely clear the polling_places table
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
        logger.info("Completely clearing polling_places table before loading new data")
        cursor.execute("DELETE FROM polling_places")
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        count = cursor.fetchone()[0]
        logger.info(f"Polling places table has {count} records after clearing")
        
        conn.close()
        
        download_success = download_polling_places_data()
        load_success = False
        
        if download_success:
            polling_places_path = DATA_DIR / "polling_places" / "polling-places-2025.csv"
            if polling_places_path.exists():
                polling_places = process_polling_places_file(polling_places_path)
                if polling_places:
                    logger.info(f"Processed {len(polling_places)} valid polling places from 2025 data")
                    load_success = save_polling_places_to_database(polling_places)
                    if not load_success:
                        logger.error("Failed to save 2025 polling places to database")
        
        
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
        logger.info("Performing final cleanup to remove any empty records")
        cursor.execute("""
        DELETE FROM polling_places 
        WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
              division_name = '' OR polling_place_name = ''
        """)
        removed = cursor.rowcount
        logger.info(f"Removed {removed} empty records during final cleanup")
        
        cursor.execute("""
        SELECT COUNT(*) FROM polling_places 
        WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
              division_name = '' OR polling_place_name = ''
        """)
        empty_count = cursor.fetchone()[0]
        logger.info(f"Verified {empty_count} empty records remain after cleanup")
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        total_count = cursor.fetchone()[0]
        logger.info(f"Total of {total_count} polling places in database after loading")
        
        cursor.execute("""
        SELECT polling_place_id, polling_place_name, division_name 
        FROM polling_places 
        WHERE polling_place_name LIKE '%North Sydney%' 
           OR polling_place_name LIKE '%Cammeray%' 
           OR polling_place_name LIKE '%Wollstonecraft%'
        """)
        north_sydney_booths = cursor.fetchall()
        logger.info(f"Found {len(north_sydney_booths)} North Sydney area booths:")
        for booth in north_sydney_booths:
            logger.info(f"  {booth[0]} | {booth[1]} | {booth[2]}")
        
        cursor.execute("SELECT * FROM polling_places LIMIT 3")
        sample_records = cursor.fetchall()
        for record in sample_records:
            logger.info(f"Sample record: {record}")
        
        conn.commit()
        conn.close()
        
        return load_success and empty_count == 0
    except Exception as e:
        logger.error(f"Error processing and loading polling places: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


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
        create_polling_places_table()  # Create the new polling_places table
        
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
        booth_success = save_booth_results_to_database(results)
        
        logger.info("Loading 2025 polling places data")
        polling_places_success = process_and_load_polling_places()
        
        success = booth_success and polling_places_success
        
        if success:
            logger.info("Successfully processed and loaded booth results and polling places")
        else:
            logger.error("Failed to save booth results and/or polling places to database")
            
        return success
    except Exception as e:
        logger.error(f"Error processing and loading booth results: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    process_and_load_booth_results()
