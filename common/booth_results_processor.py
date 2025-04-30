"""
Booth Results Processor

This utility processes booth-level results from the 2022 federal election
and provides functionality to calculate swings between historical and current results.
"""

import os
import csv
import json
import logging
import random
import sqlite3
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

AEC_BOOTH_RESULTS_URL = "https://results.aec.gov.au/27966/Website/Downloads/HouseTppByPollingPlaceDownload-27966.csv"

DATA_DIR = Path(__file__).parent.parent / "data"
is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent.parent / "data")
DB_PATH = Path(f"{data_dir_path}/results.db")
logger.info(f"Using database path: {DB_PATH}, exists: {DB_PATH.exists()}")
logger.info(f"Current working directory: {os.getcwd()}")


def ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA_DIR, 0o777)  # Full permissions for the data directory
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
        logger.info(
            f"DATA_DIR: {DATA_DIR}, exists: {DATA_DIR.exists()}, is_dir: {DATA_DIR.is_dir()}"
        )
        logger.info(f"Current working directory: {os.getcwd()}")

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(AEC_BOOTH_RESULTS_URL, stream=True)
            response.raise_for_status()

            with open(booth_results_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(
                f"Successfully downloaded booth results file to {booth_results_path}"
            )
            logger.info(
                f"File exists: {booth_results_path.exists()}, size: {booth_results_path.stat().st_size if booth_results_path.exists() else 0} bytes"
            )
            return True
        except requests.exceptions.RequestException as re:
            logger.error(f"Request error downloading booth results file: {re}")
            return False
    except Exception as e:
        logger.error(f"Error downloading booth results file: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


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

        cursor.execute(
            """
        SELECT * FROM tcp_candidates 
        WHERE electorate = ? 
        ORDER BY id
        """,
            (division_name,),
        )

        rows = cursor.fetchall()
        results = [dict(row) for row in rows]

        conn.close()
        logger.info(f"Found {len(results)} TCP candidates for division {division_name}")
        return results
    except Exception as e:
        logger.error(f"Error getting TCP candidates for division {division_name}: {e}")
        return []


def calculate_swing(
    current_result: Dict[str, Any], historical_result: Dict[str, Any]
) -> float:
    """
    Calculate the swing between current and historical results.

    Args:
        current_result: Current election result
        historical_result: Historical (2022) election result

    Returns:
        float: Calculated swing percentage
    """
    try:
        current_liberal_pct = current_result.get("liberal_national_percentage", 0)
        current_labor_pct = current_result.get("labor_percentage", 0)

        historical_liberal_pct = historical_result.get("liberal_national_percentage", 0)
        historical_labor_pct = historical_result.get("labor_percentage", 0)

        swing = current_labor_pct - historical_labor_pct

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

        cursor.execute(
            """
        SELECT * FROM polling_places 
        WHERE polling_place_id = ?
        """,
            (polling_place_id,),
        )

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

        required_columns = {
            "status",
            "wheelchair_access",
            "address",
            "latitude",
            "longitude",
        }
        missing_columns = required_columns - columns

        if columns and missing_columns:
            logger.info(
                f"Polling places table exists but is missing columns: {missing_columns}"
            )
            logger.info(
                "Dropping and recreating polling_places table with correct schema"
            )
            cursor.execute("DROP TABLE polling_places")
            conn.commit()

        cursor.execute(
            """
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
        """
        )

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

        polling_places_url = (
            "https://www.aec.gov.au/election/files/polling-places-2025.csv"
        )
        polling_places_path = polling_places_dir / "polling-places-2025.csv"

        if polling_places_path.exists():
            try:
                with open(polling_places_path, "r", encoding="utf-8-sig") as f:
                    first_line = f.readline().strip()
                    if (
                        first_line.startswith("<!DOCTYPE html>")
                        or "<html" in first_line
                    ):
                        logger.warning(
                            f"Existing polling places file contains HTML instead of CSV data. Deleting and re-downloading."
                        )
                        polling_places_path.unlink()  # Delete the corrupted file
                    else:
                        logger.info(
                            f"Polling places file already exists at {polling_places_path} and appears to be valid CSV"
                        )
                        return True
            except Exception as e:
                logger.warning(f"Error checking existing polling places file: {e}")
                polling_places_path.unlink()  # Delete the potentially corrupted file

        potential_urls = [
            "https://www.aec.gov.au/About_AEC/cea-notices/files/2025/prdelms.gaz.statics.250428.09.00.02.csv",
            "https://www.aec.gov.au/election/files/polling-places-2025.csv",
            "https://www.aec.gov.au/About_AEC/cea-notices/files/polling-places-2025.csv",
            "https://www.aec.gov.au/Elections/federal_elections/2025/files/polling-places.csv",
        ]

        download_success = False
        for url in potential_urls:
            try:
                logger.info(f"Attempting to download polling places data from {url}")
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                content_preview = response.content[:100].decode(
                    "utf-8", errors="ignore"
                )

                if (
                    "text/html" in content_type
                    or content_preview.startswith("<!DOCTYPE html>")
                    or "<html" in content_preview
                ):
                    logger.warning(
                        f"URL {url} returned HTML instead of CSV data. Skipping."
                    )
                    continue

                with open(polling_places_path, "wb") as f:
                    f.write(response.content)

                with open(polling_places_path, "r", encoding="utf-8-sig") as f:
                    first_line = f.readline().strip()
                    if (
                        first_line.startswith("<!DOCTYPE html>")
                        or "<html" in first_line
                    ):
                        logger.warning(
                            f"Downloaded file from {url} contains HTML instead of CSV data. Skipping."
                        )
                        polling_places_path.unlink()  # Delete the corrupted file
                        continue

                logger.info(
                    f"Successfully downloaded polling places data from {url} to {polling_places_path}"
                )
                download_success = True
                break
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Could not download polling places data from {url}: {e}"
                )

        if download_success:
            return True

        logger.warning(
            "All download attempts failed. Checking for local copy of the polling places data..."
        )

        possible_paths = [
            Path("~/browser_downloads/polling-places-2025.csv").expanduser(),
            Path("/home/ubuntu/browser_downloads/polling-places-2025.csv"),
            Path("/tmp/polling-places-2025.csv"),
            Path(
                "~/browser_downloads/prdelms.gaz.statics.250428.09.00.02.csv"
            ).expanduser(),
            Path(
                "/home/ubuntu/browser_downloads/prdelms.gaz.statics.250428.09.00.02.csv"
            ),
            Path("/tmp/prdelms.gaz.statics.250428.09.00.02.csv"),
        ]

        for local_copy in possible_paths:
            if local_copy.exists():
                logger.info(f"Found local copy of polling places data at {local_copy}")

                try:
                    with open(local_copy, "r", encoding="utf-8-sig") as f:
                        first_line = f.readline().strip()
                        if (
                            first_line.startswith("<!DOCTYPE html>")
                            or "<html" in first_line
                        ):
                            logger.warning(
                                f"Local file {local_copy} contains HTML instead of CSV data. Skipping."
                            )
                            continue
                except Exception as e:
                    logger.warning(f"Error checking local file {local_copy}: {e}")
                    continue

                import shutil

                shutil.copy(local_copy, polling_places_path)
                logger.info(
                    f"Copied local polling places data to {polling_places_path}"
                )
                return True

        logger.info(
            f"Checked these paths for local polling places data: {possible_paths}"
        )
        logger.error(f"All download attempts failed and no valid local copy found.")
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
        with open(file_path, "r", encoding="utf-8-sig") as f:
            import csv

            reader = csv.DictReader(f)

            headers = reader.fieldnames
            logger.info(f"CSV headers: {headers}")

            valid_count = 0
            skipped_count = 0

            for row in reader:
                try:
                    if row.get("Status") == "Abolition":
                        skipped_count += 1
                        continue

                    if not row.get("PPId") or not row.get("DivName"):
                        skipped_count += 1
                        continue

                    division_name = row.get("DivName", "").strip()

                    polling_place_name = row.get("PPName", "").strip()
                    if " (" in polling_place_name:
                        polling_place_name = polling_place_name.split(" (")[0].strip()

                    address_parts = []
                    if row.get("PremisesName"):
                        address_parts.append(row.get("PremisesName").strip())
                    if row.get("Address1"):
                        address_parts.append(row.get("Address1").strip())
                    if row.get("Address2") and row.get("Address2").strip():
                        address_parts.append(row.get("Address2").strip())
                    if row.get("Address3") and row.get("Address3").strip():
                        address_parts.append(row.get("Address3").strip())
                    if row.get("Locality"):
                        address_parts.append(row.get("Locality").strip())
                    if row.get("AddrStateAb"):
                        address_parts.append(row.get("AddrStateAb").strip())
                    if row.get("Postcode"):
                        address_parts.append(row.get("Postcode").strip())

                    address = ", ".join(
                        [part for part in address_parts if part and part.strip()]
                    )

                    try:
                        polling_place_id = int(row.get("PPId", 0))
                        if polling_place_id <= 0:
                            logger.warning(
                                f"Invalid polling place ID: {polling_place_id}, skipping row"
                            )
                            skipped_count += 1
                            continue
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid polling place ID format: {row.get('PPId')}, skipping row"
                        )
                        skipped_count += 1
                        continue

                    try:
                        division_id = int(row.get("DivId", 0))
                    except (ValueError, TypeError):
                        division_id = 0

                    try:
                        latitude = (
                            float(row.get("Lat", 0))
                            if row.get("Lat") and row.get("Lat").strip()
                            else None
                        )
                    except (ValueError, TypeError):
                        latitude = None

                    try:
                        longitude = (
                            float(row.get("Long", 0))
                            if row.get("Long") and row.get("Long").strip()
                            else None
                        )
                    except (ValueError, TypeError):
                        longitude = None

                    place = {
                        "state": row.get("StateAb", "").strip(),
                        "division_id": division_id,
                        "division_name": division_name,
                        "polling_place_id": polling_place_id,
                        "polling_place_name": polling_place_name,
                        "address": address,
                        "latitude": latitude,
                        "longitude": longitude,
                        "status": row.get("Status", "").strip(),
                        "wheelchair_access": row.get("WheelchairAccess", "").strip(),
                    }

                    if (
                        not place["state"]
                        or not place["division_name"]
                        or not place["polling_place_name"]
                    ):
                        logger.warning(
                            f"Missing required fields in row, skipping: {place}"
                        )
                        skipped_count += 1
                        continue

                    if (
                        "North Sydney" in polling_place_name
                        or "Cammeray" in polling_place_name
                        or "Wollstonecraft" in polling_place_name
                    ):
                        logger.info(
                            f"North Sydney area booth in CSV: {polling_place_id} | {polling_place_name} | Division: {division_name} | Row data: {row}"
                        )

                    polling_places.append(place)
                    valid_count += 1

                    if valid_count % 100 == 0:
                        logger.info(
                            f"Processed {valid_count} valid polling places so far"
                        )

                except Exception as e:
                    logger.warning(f"Error processing row: {row}, error: {e}")
                    skipped_count += 1
                    continue

        logger.info(
            f"Processed {len(polling_places)} valid polling places from file (skipped {skipped_count})"
        )

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
            if (
                not place.get("state")
                or not place.get("division_name")
                or not place.get("polling_place_name")
                or place.get("polling_place_id", 0) <= 0
                or place.get("division_id", 0) <= 0
            ):
                invalid_count += 1
                continue

            valid_polling_places.append(place)

        logger.info(
            f"Filtered out {invalid_count} invalid records, proceeding with {len(valid_polling_places)} valid records"
        )

        for place in valid_polling_places:
            cursor.execute(
                """
            INSERT INTO polling_places
            (state, division_id, division_name, polling_place_id, polling_place_name, 
             address, latitude, longitude, status, wheelchair_access, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    place["state"],
                    place["division_id"],
                    place["division_name"],
                    place["polling_place_id"],
                    place["polling_place_name"],
                    place.get("address", ""),
                    place.get("latitude"),
                    place.get("longitude"),
                    place.get("status", "Current"),
                    place.get("wheelchair_access", ""),
                    json.dumps(place),
                ),
            )

        conn.commit()

        cursor.execute(
            """
        SELECT COUNT(*) FROM polling_places 
        WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
              division_name = '' OR polling_place_name = ''
        """
        )
        empty_count = cursor.fetchone()[0]

        if empty_count > 0:
            logger.warning(
                f"Found {empty_count} empty records after insertion, removing them"
            )
            cursor.execute(
                """
            DELETE FROM polling_places 
            WHERE state = '' OR division_id = 0 OR polling_place_id = 0 OR 
                  division_name = '' OR polling_place_name = ''
            """
            )
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

        cursor.execute(
            """
        SELECT * FROM polling_places 
        WHERE division_name = ? 
        ORDER BY polling_place_name
        """,
            (division_name,),
        )

        rows = cursor.fetchall()
        polling_places = [dict(row) for row in rows]

        conn.close()
        logger.info(
            f"Found {len(polling_places)} polling places for division {division_name}"
        )
        return polling_places
    except Exception as e:
        logger.error(f"Error getting polling places for division {division_name}: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return []  # Return empty list


def create_sample_2025_polling_places_data() -> List[Dict[str, Any]]:
    """
    Create a sample dataset for 2025 polling places without using 2022 data.

    Returns:
        List[Dict[str, Any]]: List of polling place dictionaries
    """
    try:
        logger.info("Creating sample 2025 polling places dataset")

        sample_divisions = {
            "Warringah": {"id": 151, "state": "NSW"},
            "Bradfield": {"id": 103, "state": "NSW"},
            "North Sydney": {"id": 134, "state": "NSW"},
            "Bennelong": {"id": 102, "state": "NSW"},
            "Mackellar": {"id": 127, "state": "NSW"},
        }

        sample_polling_places = []
        polling_place_id = 50000  # Start with a high ID to avoid conflicts

        warringah_places = [
            "Allambie",
            "Allambie Heights",
            "Balgowlah",
            "Balgowlah East",
            "Balgowlah Heights",
            "Balmoral",
            "Beacon Hill",
            "Beauty Point",
            "Brookvale",
            "Clontarf",
            "Collaroy",
            "Collaroy Plateau",
            "Curl Curl",
            "Dee Why",
            "Fairlight",
            "Forestville",
            "Frenchs Forest",
            "Killarney Heights",
            "Manly",
            "Manly Vale",
            "North Balgowlah",
            "North Curl Curl",
            "North Manly",
            "Queenscliff",
            "Seaforth",
            "Wollstonecraft",
            "North Sydney",
        ]

        for place_name in warringah_places:
            polling_place_id += 1
            sample_polling_places.append(
                {
                    "state": "NSW",
                    "division_id": 151,  # Warringah
                    "division_name": "Warringah",
                    "polling_place_id": polling_place_id,
                    "polling_place_name": place_name,
                    "status": "Current",
                    "wheelchair_access": "Yes" if random.random() > 0.2 else "No",
                    "address": f"{place_name} Polling Place, Warringah, NSW",
                }
            )

        bradfield_places = [
            "Cammeray",
            "Chatswood",
            "East Lindfield",
            "Gordon",
            "Killara",
            "Lindfield",
            "Pymble",
            "Roseville",
            "St Ives",
            "Turramurra",
            "Wahroonga",
            "Waitara",
            "Warrawee",
            "West Pymble",
        ]

        for place_name in bradfield_places:
            polling_place_id += 1
            sample_polling_places.append(
                {
                    "state": "NSW",
                    "division_id": 103,  # Bradfield
                    "division_name": "Bradfield",
                    "polling_place_id": polling_place_id,
                    "polling_place_name": place_name,
                    "status": "Current",
                    "wheelchair_access": "Yes" if random.random() > 0.2 else "No",
                    "address": f"{place_name} Polling Place, Bradfield, NSW",
                }
            )

        sample_polling_places.append(
            {
                "state": "NSW",
                "division_id": 103,  # Bradfield
                "division_name": "Bradfield",
                "polling_place_id": 121997,
                "polling_place_name": "Cammeray",
                "status": "Current",
                "wheelchair_access": "Yes",
                "address": "Cammeray Polling Place, Bradfield, NSW",
            }
        )

        logger.info(
            f"Created sample dataset with {len(sample_polling_places)} polling places for 2025"
        )
        return sample_polling_places
    except Exception as e:
        logger.error(f"Error creating sample 2025 polling places data: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return []


def add_prepoll_booths() -> bool:
    """Add pre-poll booths for each division."""
    try:
        logger.info("Adding pre-poll booths for each division")
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Get all unique divisions
        cursor.execute("SELECT DISTINCT division_name FROM polling_places")
        divisions = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(divisions)} divisions")

        # For each division, add a pre-poll booth if it doesn't exist
        for division in divisions:
            prepoll_name = f"Pre-Poll-{division}"

            # Check if pre-poll booth already exists
            cursor.execute(
                "SELECT COUNT(*) FROM polling_places WHERE division_name = ? AND polling_place_name = ?",
                (division, prepoll_name),
            )
            exists = cursor.fetchone()[0] > 0

            if not exists:
                # Get max polling_place_id for this division
                cursor.execute(
                    "SELECT MAX(polling_place_id) FROM polling_places WHERE division_name = ?",
                    (division,),
                )
                max_id = cursor.fetchone()[0] or 0
                new_id = max_id + 1

                # Insert pre-poll booth
                cursor.execute(
                    """
                    INSERT INTO polling_places (
                        state,
                        division_id,
                        division_name,
                        polling_place_id,
                        polling_place_name,
                        address,
                        status,
                        wheelchair_access,
                        data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        "NSW",  # State
                        0,  # Division ID (placeholder)
                        division,
                        new_id,
                        prepoll_name,
                        f"Pre-poll voting center for {division}",
                        "ACTIVE",
                        "Yes",
                        json.dumps({"type": "pre-poll"}),
                    ),
                )
                logger.info(f"Added pre-poll booth for {division}")

        conn.commit()
        conn.close()
        logger.info("Successfully added pre-poll booths")
        return True

    except Exception as e:
        logger.error(f"Error adding pre-poll booths: {e}")
        return False


def process_and_load_polling_places() -> bool:
    """
    Process and load polling places data.
    Tries to download 2025 polling places data from AEC.
    Falls back to sample 2025 data if download fails.

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

        # Download and process polling places
        success = download_polling_places_data()
        if not success:
            logger.error("Failed to download polling places data")
            return False

        # Add pre-poll booths
        success = add_prepoll_booths()
        if not success:
            logger.error("Failed to add pre-poll booths")
            return False

        return True
    except Exception as e:
        logger.error(f"Error processing and loading polling places: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def process_and_load_booth_results() -> bool:
    """
    Process and load polling places data for the 2025 federal election.

    Returns:
        bool: True if all operations were successful, False otherwise
    """
    try:
        ensure_data_dir()
        create_polling_places_table()

        logger.info("Loading 2025 polling places data")
        polling_places_success = process_and_load_polling_places()

        if polling_places_success:
            logger.info("Successfully processed and loaded polling places")
        else:
            logger.error("Failed to load polling places data")

        return polling_places_success
    except Exception as e:
        logger.error(f"Error processing and loading data: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    process_and_load_booth_results()
