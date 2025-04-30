import sqlite3
import os


def check_prepoll_booths():
    db_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "results.db"
    )
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count total polling places
    cursor.execute("SELECT COUNT(*) FROM polling_places")
    total = cursor.fetchone()[0]
    print(f"Total polling places: {total}")

    # Count pre-poll booths
    cursor.execute(
        "SELECT COUNT(*) FROM polling_places WHERE polling_place_name LIKE 'Pre-Poll%'"
    )
    prepoll = cursor.fetchone()[0]
    print(f"Pre-poll booths: {prepoll}")

    # Get a sample of pre-poll booths
    cursor.execute(
        "SELECT polling_place_name, division_name FROM polling_places WHERE polling_place_name LIKE 'Pre-Poll%' LIMIT 5"
    )
    print("\nSample pre-poll booths:")
    for row in cursor.fetchall():
        print(f"- {row[0]} in {row[1]}")

    conn.close()


if __name__ == "__main__":
    check_prepoll_booths()
