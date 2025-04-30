"""
Candidate Data Loader

This utility loads candidate data for the 2025 federal election.
"""

import os
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Use the same database path as FastAPI
is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = (
    "/app/data" if is_docker else str(Path(__file__).parent.parent.parent / "data")
)
DB_PATH = Path(data_dir_path) / "results.db"

logger.info(f"Using database path: {DB_PATH}, exists: {DB_PATH.exists()}")


def create_candidates_table() -> None:
    """Create the candidates table in the SQLite database if it doesn't exist."""
    try:
        logger.info(f"Creating candidates table in database: {DB_PATH}")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()

        cursor.execute(
            """
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
        """
        )

        conn.commit()
        conn.close()
        logger.info("Successfully created candidates table")
    except Exception as e:
        logger.error(f"Error creating candidates table: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")


def load_sample_candidates() -> bool:
    """
    Load sample candidate data for testing purposes.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Loading sample candidate data")
        db_path_str = str(DB_PATH)
        conn = sqlite3.connect(db_path_str)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM candidates WHERE electorate = 'Warringah'")
        count = cursor.fetchone()[0]

        if count > 0:
            logger.info(
                f"Found {count} existing candidates for Warringah, skipping sample data load"
            )
            conn.close()
            return True

        warringah_candidates = [
            {
                "candidate_name": "STEGGALL, Zali",
                "party": "Independent",
                "electorate": "Warringah",
                "ballot_position": 1,
                "candidate_type": "house",
                "state": "NSW",
            },
            {
                "candidate_name": "ROGERS, Katherine",
                "party": "Liberal Party",
                "electorate": "Warringah",
                "ballot_position": 2,
                "candidate_type": "house",
                "state": "NSW",
            },
            {
                "candidate_name": "SMITH, John",
                "party": "Australian Labor Party",
                "electorate": "Warringah",
                "ballot_position": 3,
                "candidate_type": "house",
                "state": "NSW",
            },
            {
                "candidate_name": "JONES, Sarah",
                "party": "The Greens",
                "electorate": "Warringah",
                "ballot_position": 4,
                "candidate_type": "house",
                "state": "NSW",
            },
            {
                "candidate_name": "BROWN, Michael",
                "party": "One Nation",
                "electorate": "Warringah",
                "ballot_position": 5,
                "candidate_type": "house",
                "state": "NSW",
            },
        ]

        for candidate in warringah_candidates:
            cursor.execute(
                """
            INSERT INTO candidates (
                candidate_name, party, electorate, ballot_position, candidate_type, state
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    candidate["candidate_name"],
                    candidate["party"],
                    candidate["electorate"],
                    candidate["ballot_position"],
                    candidate["candidate_type"],
                    candidate["state"],
                ),
            )

        tcp_candidates = [
            {
                "electorate": "Warringah",
                "candidate_name": "STEGGALL, Zali",
                "party": "Independent",
            },
            {
                "electorate": "Warringah",
                "candidate_name": "ROGERS, Katherine",
                "party": "Liberal Party",
            },
        ]

        cursor.execute(
            "SELECT COUNT(*) FROM tcp_candidates WHERE electorate = 'Warringah'"
        )
        tcp_count = cursor.fetchone()[0]

        if tcp_count == 0:
            for tcp_candidate in tcp_candidates:
                cursor.execute(
                    """
                INSERT INTO tcp_candidates (
                    electorate, candidate_name, party
                ) VALUES (?, ?, ?)
                """,
                    (
                        tcp_candidate["electorate"],
                        tcp_candidate["candidate_name"],
                        tcp_candidate["party"],
                    ),
                )

        conn.commit()
        conn.close()

        logger.info(
            f"Successfully loaded {len(warringah_candidates)} sample candidates for Warringah"
        )
        return True
    except Exception as e:
        logger.error(f"Error loading sample candidate data: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def process_and_load_candidate_data() -> bool:
    """
    Process and load candidate data for the 2025 federal election.

    Returns:
        bool: True if all operations were successful, False otherwise
    """
    try:
        create_candidates_table()
        return load_sample_candidates()
    except Exception as e:
        logger.error(f"Error processing and loading candidate data: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    process_and_load_candidate_data()
