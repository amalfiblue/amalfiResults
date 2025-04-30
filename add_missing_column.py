import os
import sqlite3
from pathlib import Path

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent / "data")
db_path = f"{data_dir_path}/results.db"

print(f"Using database at: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(results)")
    columns = [column[1] for column in cursor.fetchall()]

    print(f"Current columns in results table: {columns}")

    if "is_reviewed" not in columns:
        print("Adding missing 'is_reviewed' column...")
        cursor.execute("ALTER TABLE results ADD COLUMN is_reviewed INTEGER DEFAULT 0")
        conn.commit()
        print("Column added successfully!")
    else:
        print("Column 'is_reviewed' already exists.")

    if "reviewer" not in columns:
        print("Adding missing 'reviewer' column...")
        cursor.execute("ALTER TABLE results ADD COLUMN reviewer TEXT")
        conn.commit()
        print("Column added successfully!")
    else:
        print("Column 'reviewer' already exists.")

    if "aec_booth_name" not in columns:
        print("Adding missing 'aec_booth_name' column...")
        cursor.execute("ALTER TABLE results ADD COLUMN aec_booth_name TEXT")
        conn.commit()
        print("Column 'aec_booth_name' added successfully!")
    else:
        print("Column 'aec_booth_name' already exists.")

    cursor.execute("PRAGMA table_info(results)")
    updated_columns = [column[1] for column in cursor.fetchall()]
    print(f"Updated columns in results table: {updated_columns}")

    conn.close()
    print("Database migration completed successfully!")

except Exception as e:
    print(f"Error: {e}")
