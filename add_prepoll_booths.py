import sqlite3
import json
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_prepoll_booths():
    """Add pre-poll booths for each division."""
    try:
        logger.info("Adding pre-poll booths for each division")
        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "results.db"
        )
        logger.info(f"Using database at: {db_path}")
        conn = sqlite3.connect(db_path)
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


if __name__ == "__main__":
    add_prepoll_booths()
