import os
import sqlite3
from pathlib import Path
import json

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent / "flask_app")
db_path = f"{data_dir_path}/results.db"

print(f"Using database at: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='results'")
    if not cursor.fetchone():
        print("Results table doesn't exist. Creating it...")
        cursor.execute("""
        CREATE TABLE results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            electorate VARCHAR,
            booth_name VARCHAR,
            timestamp DATETIME,
            image_url VARCHAR,
            is_reviewed INTEGER DEFAULT 0,
            reviewer VARCHAR,
            data VARCHAR
        )
        """)
        conn.commit()
        print("Results table created successfully!")
    else:
        print("Results table exists. Checking columns...")
        
        cursor.execute("PRAGMA table_info(results)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"Current columns in results table: {columns}")
        
        if "is_reviewed" not in columns:
            print("Adding missing 'is_reviewed' column...")
            cursor.execute("ALTER TABLE results ADD COLUMN is_reviewed INTEGER DEFAULT 0")
            conn.commit()
            print("Column 'is_reviewed' added successfully!")
        
        if "reviewer" not in columns:
            print("Adding missing 'reviewer' column...")
            cursor.execute("ALTER TABLE results ADD COLUMN reviewer VARCHAR")
            conn.commit()
            print("Column 'reviewer' added successfully!")
        
        cursor.execute("PRAGMA table_info(results)")
        updated_columns = [column[1] for column in cursor.fetchall()]
        print(f"Updated columns in results table: {updated_columns}")
    
    cursor.execute("SELECT COUNT(*) FROM results")
    row_count = cursor.fetchone()[0]
    print(f"Number of rows in results table: {row_count}")
    
    print("Creating indexes if they don't exist...")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_results_id ON results (id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_results_electorate ON results (electorate)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_results_booth_name ON results (booth_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_results_image_url ON results (image_url)")
    conn.commit()
    print("Indexes created successfully!")
    
    print("\nTo fix the Flask app's Result class, add these attributes to the __init__ method:")
    print("self.is_reviewed = kwargs.get('is_reviewed', 0)")
    print("self.reviewer = kwargs.get('reviewer')")
    print("\nAnd add them to the to_dict method:")
    print("'is_reviewed': self.is_reviewed,")
    print("'reviewer': self.reviewer,")
    
    conn.close()
    print("\nDatabase migration completed successfully!")
    
except Exception as e:
    print(f"Error: {e}")
