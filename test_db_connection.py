import os
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent / "flask_app")
db_path = f"{data_dir_path}/results.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

print(f"Using database at: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

try:
    print("\n--- Testing direct SQLite connection ---")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(results)")
    columns = [column[1] for column in cursor.fetchall()]
    print(f"Columns in results table: {columns}")
    
    try:
        cursor.execute("SELECT id, electorate, booth_name, is_reviewed FROM results LIMIT 5")
        rows = cursor.fetchall()
        print(f"Query successful, found {len(rows)} rows")
        if rows:
            print(f"Sample row: {rows[0]}")
    except Exception as e:
        print(f"SQLite query error: {e}")
    
    conn.close()
    
    print("\n--- Testing SQLAlchemy connection ---")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        result = session.execute(text("SELECT id, electorate, booth_name, is_reviewed FROM results LIMIT 5"))
        rows = result.fetchall()
        print(f"SQLAlchemy query successful, found {len(rows)} rows")
        if rows:
            print(f"Sample row: {rows[0]}")
    except Exception as e:
        print(f"SQLAlchemy query error: {e}")
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {str(e)}")
    
    session.close()
    
except Exception as e:
    print(f"Error: {e}")
