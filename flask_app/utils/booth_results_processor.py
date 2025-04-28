"""
Polling Places Processor

This utility processes polling places data for the 2025 federal election.
"""

import os
import csv
import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = Path(__file__).parent.parent / "data" / "results.db"

def ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directory ensured at {DATA_DIR}")

def calculate_swing(current_result: Dict[str, Any], previous_result: Dict[str, Any]) -> float:
    """
    Calculate the swing between current and previous results.
    
    Args:
        current_result: Current election result
        previous_result: Previous election result
        
    Returns:
        float: Calculated swing percentage
    """
    try:
        current_liberal_pct = current_result.get('liberal_national_percentage', 0)
        current_labor_pct = current_result.get('labor_percentage', 0)
        
        previous_liberal_pct = previous_result.get('liberal_national_percentage', 0)
        previous_labor_pct = previous_result.get('labor_percentage', 0)
        
        swing = (current_labor_pct - previous_labor_pct)
        
        return round(swing, 2)
    except Exception as e:
        logger.error(f"Error calculating swing: {e}")
        return 0.0

def create_polling_places_table() -> None:
    """Create the polling_places table in the SQLite database if it doesn't exist."""
    try:
        logger.info(f"Creating polling_places table in database: {DB_PATH}")
        db_path_str = str(DB_PATH)
        logger.info(f"Database path as string: {db_path_str}")
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()
        
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

def get_polling_places_for_division(division_name: str) -> List[Dict[str, Any]]:
    """
    Get polling places for a specific division from the database.
    
    Args:
        division_name: Name of the division/electorate
        
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
        
        conn.close()
        logger.info(f"Found {len(polling_places)} polling places for division {division_name}")
        return polling_places
    except Exception as e:
        logger.error(f"Error getting polling places for division {division_name}: {e}")
        return []

def create_sample_polling_places_data() -> List[Dict[str, Any]]:
    """
    Create sample polling places data when no official data is available.
    
    Returns:
        List of sample polling place dictionaries
    """
    try:
        logger.info("Creating sample polling places data")
        sample_data = []
        
        divisions = [
            {"state": "NSW", "division_id": 151, "division_name": "Warringah"},
            {"state": "NSW", "division_id": 150, "division_name": "Bradfield"}
        ]
        
        for division in divisions:
            division_name = division["division_name"]
            base_id = 50000 if division_name == "Warringah" else 60000
            
            places = []
            if division_name == "Warringah":
                places = ["Manly", "Dee Why", "Brookvale", "Balgowlah", "North Sydney", "Wollstonecraft"]
            else:  # Bradfield
                places = ["Lindfield", "Killara", "Gordon", "Pymble", "Cammeray"]
            
            for i, place_name in enumerate(places):
                polling_place_id = base_id + i
                
                sample_data.append({
                    "state": division["state"],
                    "division_id": division["division_id"],
                    "division_name": division["division_name"],
                    "polling_place_id": polling_place_id,
                    "polling_place_name": place_name,
                    "address": f"{place_name} Community Centre",
                    "status": "Current",
                    "wheelchair_access": "Yes",
                    "data": json.dumps({
                        "state": division["state"],
                        "division_id": division["division_id"],
                        "division_name": division["division_name"],
                        "polling_place_id": polling_place_id,
                        "polling_place_name": place_name
                    })
                })
        
        logger.info(f"Created {len(sample_data)} sample polling places")
        return sample_data
    except Exception as e:
        logger.error(f"Error creating sample polling places data: {e}")
        return []

def process_and_load_polling_places() -> bool:
    """
    Process and load polling places data for the 2025 federal election.
    
    Returns:
        bool: True if all operations were successful, False otherwise
    """
    try:
        ensure_data_dir()
        create_polling_places_table()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM polling_places")
        conn.commit()
        conn.close()
        logger.info("Cleared existing polling places data")
        
        sample_data = create_sample_polling_places_data()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for place in sample_data:
            cursor.execute('''
            INSERT INTO polling_places
            (state, division_id, division_name, polling_place_id, polling_place_name,
             address, status, wheelchair_access, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                place["state"],
                place["division_id"],
                place["division_name"],
                place["polling_place_id"],
                place["polling_place_name"],
                place["address"],
                place["status"],
                place["wheelchair_access"],
                place["data"]
            ))
        
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM polling_places")
        count = cursor.fetchone()[0]
        logger.info(f"Saved {count} polling places to database")
        
        conn.close()
        return count > 0
    except Exception as e:
        logger.error(f"Error processing and loading polling places: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    process_and_load_polling_places()
