import os
import re
import sqlite3
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
from PIL import Image
import pytesseract
import io
import json
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    Float,
    Boolean,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import logging
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel
from utils.image_processor import ImageProcessor
from collections import defaultdict

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tally Sheet Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

is_docker = os.path.exists("/.dockerenv") or os.path.isdir("/app/data")
data_dir_path = "/app/data" if is_docker else str(Path(__file__).parent.parent / "data")
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{data_dir_path}/results.db"
)
logger.info(f"Running in {'Docker' if is_docker else 'local'} environment")
logger.info(f"Using database path: {data_dir_path}/results.db")
logger.info(f"Database URL: {SQLALCHEMY_DATABASE_URL}")
logger.info(f"Database file exists: {os.path.exists(f'{data_dir_path}/results.db')}")

data_dir = Path(data_dir_path)
data_dir.mkdir(parents=True, exist_ok=True)
os.chmod(data_dir, 0o777)  # Full permissions for the data directory

# Create uploads directory
uploads_dir = Path(data_dir_path) / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
os.chmod(uploads_dir, 0o777)  # Full permissions for the uploads directory

# Mount the uploads directory
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

import sys

sys.path.append(str(Path(__file__).parent.parent))
logger.info(
    f"Adding parent directory to Python path: {str(Path(__file__).parent.parent)}"
)
from utils.booth_results_processor import process_and_load_booth_results
from utils.candidate_data_loader import process_and_load_candidate_data

# Initialize database engine and session
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize image processor
image_processor = ImageProcessor()


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, index=True)
    electorate = Column(String, index=True)
    booth_name = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String, index=True)
    is_reviewed = Column(Integer, default=0)  # SQLite stores BOOLEAN as INTEGER
    reviewer = Column(String)
    data = Column(String)  # SQLite stores JSON as TEXT


class TCPCandidate(Base):
    __tablename__ = "tcp_candidates"

    id = Column(Integer, primary_key=True, index=True)
    electorate = Column(String, index=True)
    candidate_name = Column(String)
    party = Column(String)


class TCPCandidateCreate(BaseModel):
    electorate: str
    candidate_name: str
    party: str


class TCPCandidateResponse(BaseModel):
    id: int
    electorate: str
    candidate_name: str
    party: str


class ResultResponse(BaseModel):
    id: int
    image_url: Optional[str] = None
    timestamp: str
    electorate: Optional[str] = None
    booth_name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


def create_candidates_table() -> None:
    """Create the candidates table in the SQLite database if it doesn't exist."""
    try:
        logger.info(
            f"Creating candidates table in database at: {SQLALCHEMY_DATABASE_URL}"
        )
        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        logger.info(f"Database file exists: {os.path.exists(db_path)}")
        if os.path.exists(db_path):
            logger.info(f"File permissions: {oct(os.stat(db_path).st_mode)}")
            logger.info(f"File owner: {os.stat(db_path).st_uid}")

        conn = sqlite3.connect(db_path)
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


try:
    logger.info("Creating candidates table if it doesn't exist")
    create_candidates_table()
    logger.info("Candidates table creation completed")
except Exception as e:
    logger.error(f"Error creating candidates table: {e}")
    import traceback

    logger.error(f"Traceback: {traceback.format_exc()}")

import re
from typing import List, Dict, Any


def extract_tally_sheet_data(
    extracted_rows: List[Dict[str, Any]], booth_name: str
) -> Dict[str, Any]:
    """
    Extract structured data from tally sheet rows, with cleaned table preview logging.
    """
    result = {
        "electorate": "Warringah",
        "booth_name": booth_name or "Unknown Booth",
        "primary_votes": {},
        "two_candidate_preferred": {},
        "totals": {"formal": None, "informal": None, "total": None},
    }

    table_preview = []  # For logging

    # Step 1: Group extracted rows into full logical rows
    row_map = defaultdict(lambda: ["", "", "", ""])  # Assume 4 columns

    for cell in extracted_rows:
        row_idx = cell["RowIndex"]
        col_idx = cell["ColumnIndex"] - 1  # Convert to 0-based index
        if 0 <= col_idx < 4:
            row_map[row_idx][col_idx] = cell["Text"].strip()

    # Step 2: Find where candidate rows start
    table_start_idx = None
    for idx, row in row_map.items():
        if any("CANDIDATE" in col.upper() for col in row):
            table_start_idx = idx + 1  # Data starts after header
            break

    if table_start_idx is None:
        table_start_idx = min(row_map.keys())

    # Step 3: Parse candidate rows
    for idx in sorted(row_map.keys()):
        if idx < table_start_idx:
            continue

        row = row_map[idx]
        joined = " ".join(row).strip()
        upper = joined.upper()

        if not joined or "TOTAL FORMAL" in upper or "TOTAL VOTES" in upper:
            break

        logger.info(f"Full OCR Row: {repr(row)}")

        name_tokens = []
        numeric_tokens = []

        for token in row:
            clean_token = (
                token.replace("O", "0").replace("I", "1").replace("l", "1")
            )  # OCR fixes
            if re.fullmatch(r"\d+", clean_token):
                numeric_tokens.append(int(clean_token))
            else:
                name_tokens.append(token)

        if not name_tokens:
            continue

        name = " ".join(name_tokens).strip()

        if not name:
            continue

        logger.info(f"Parsed candidate: {name} | Numbers: {numeric_tokens}")

        table_preview.append([name] + numeric_tokens)

        # Primary votes = first number
        if len(numeric_tokens) >= 1:
            result["primary_votes"][name] = numeric_tokens[0]

        # Two candidate preferred (TCP) votes = next numbers
        if len(numeric_tokens) >= 3:
            result.setdefault("two_candidate_preferred", {}).setdefault("STEGGALL", {})[
                name
            ] = numeric_tokens[1]
            result.setdefault("two_candidate_preferred", {}).setdefault("ROGERS", {})[
                name
            ] = numeric_tokens[2]

    # Step 4: Parse totals from bottom
    for idx, row in row_map.items():
        row_text = " ".join(row).upper()
        for field in ["FORMAL", "INFORMAL", "TOTAL"]:
            if field in row_text:
                nums = [int(x) for x in row if x.isdigit()]
                if nums:
                    key = field.lower()
                    result["totals"][key] = nums[0]

    # Step 5: Fallbacks
    if result["totals"]["formal"] is None:
        result["totals"]["formal"] = sum(result["primary_votes"].values())

    if result["totals"]["informal"] is None:
        result["totals"]["informal"] = 10

    if result["totals"]["total"] is None:
        result["totals"]["total"] = (
            result["totals"]["formal"] + result["totals"]["informal"]
        )

    # Step 6: Log the cleaned table
    logger.info("========== CLEANED TABLE PREVIEW ==========")
    for row in table_preview:
        name = row[0]
        numbers = row[1:]
        logger.info(f"{name:<30} " + " ".join(f"{n:<5}" for n in numbers))
    logger.info("===========================================")

    return result


FLASK_APP_URL = os.environ.get("FLASK_APP_URL", "http://localhost:5000/api/notify")


@app.get("/test")
async def test_endpoint():
    """
    Simple test endpoint to verify API is working
    """
    return {"status": "ok", "message": "API is working"}


@app.get("/health")
async def health_check():
    """Health check endpoint for connectivity testing"""
    return {"status": "ok"}


from fastapi import UploadFile, File, HTTPException
import io
import os
import json
from PIL import Image
import pytesseract
import httpx


from fastapi import UploadFile, File, HTTPException
import boto3
import json
import io


@app.post("/scan-image")
async def scan_image(file: UploadFile = File(...)):
    """
    Scan uploaded tally sheet image using Amazon Textract, extract table and booth name via query.
    """
    try:
        logger.info(f"Received image upload: {file.filename}")
        contents = await file.read()

        # Process the image using the shared processor
        result = await image_processor.process_image(contents, source="upload")

        # Now pass extracted_rows to your existing extract_tally_sheet_data function
        tally_data = extract_tally_sheet_data(
            result["extracted_rows"], result.get("booth_name", None)
        )
        logger.info(
            f"Extracted tally data: electorate={tally_data.get('electorate')}, booth={tally_data.get('booth_name')}"
        )

        # Save to database
        db = SessionLocal()
        try:
            # Store the image in the uploads directory
            image_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            image_path = uploads_dir / image_filename

            # Save the image file
            with open(image_path, "wb") as f:
                f.write(contents)

            # Use the FastAPI endpoint URL
            image_url = f"/uploads/{image_filename}"

            data_json = json.dumps(
                {
                    "raw_rows": result["extracted_rows"],
                    "primary_votes": tally_data.get("primary_votes"),
                    "two_candidate_preferred": tally_data.get(
                        "two_candidate_preferred"
                    ),
                    "totals": tally_data.get("totals"),
                }
            )

            # Check for existing result for this booth
            existing_result = (
                db.query(Result)
                .filter_by(
                    electorate=tally_data.get("electorate"),
                    booth_name=result["booth_name"] or tally_data.get("booth_name"),
                )
                .first()
            )

            if existing_result:
                # Update existing result
                existing_result.image_url = image_url
                existing_result.data = data_json
                existing_result.timestamp = datetime.now(timezone.utc)
                existing_result.is_reviewed = 0  # Reset review status
                existing_result.reviewer = None
                db_result = existing_result
                logger.info(f"Updated existing result with ID: {db_result.id}")
            else:
                # Create new result
                db_result = Result(
                    image_url=image_url,
                    electorate=tally_data.get("electorate"),
                    booth_name=result["booth_name"] or tally_data.get("booth_name"),
                    data=data_json,
                )
                db.add(db_result)
                logger.info(f"Created new result with ID: {db_result.id}")

            db.commit()
            db.refresh(db_result)

            # Notify Flask app if needed
            try:
                logger.info(f"Notifying Flask app at {FLASK_APP_URL}")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        FLASK_APP_URL,
                        json={
                            "result_id": db_result.id,
                            "timestamp": db_result.timestamp.isoformat(),
                            "electorate": tally_data.get("electorate"),
                            "booth_name": result["booth_name"]
                            or tally_data.get("booth_name"),
                        },
                    )
                    logger.info(
                        f"Flask app notification response: {response.status_code}"
                    )
            except Exception as notify_err:
                logger.error(f"Failed to notify Flask app: {notify_err}")

            return {
                "status": "success",
                "result_id": db_result.id,
                "electorate": tally_data.get("electorate"),
                "booth_name": result["booth_name"] or tally_data.get("booth_name"),
                "primary_votes": tally_data.get("primary_votes"),
                "two_candidate_preferred": tally_data.get("two_candidate_preferred"),
                "totals": tally_data.get("totals"),
            }
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/inbound-sms")
async def receive_sms(request: Request):
    """
    Process SMS with attached media for tally sheet scanning
    """
    try:
        payload = await request.json()
        text = payload.get("body")
        media_urls = payload.get("media", [])

        if not media_urls:
            raise HTTPException(status_code=400, detail="No media attached to SMS")

        # Process the first image (assuming it's the tally sheet)
        result = await image_processor.process_sms_image(media_urls[0])

        # Extract structured data from the tally sheet
        tally_data = extract_tally_sheet_data(
            result["extracted_rows"], result.get("booth_name", None)
        )

        db = SessionLocal()
        try:
            image_url = media_urls[0]

            data_json = json.dumps(
                {
                    "raw_rows": result["extracted_rows"],
                    "primary_votes": tally_data.get("primary_votes"),
                    "two_candidate_preferred": tally_data.get(
                        "two_candidate_preferred"
                    ),
                    "totals": tally_data.get("totals"),
                    "text": text,
                }
            )

            # Check for existing result for this booth
            existing_result = (
                db.query(Result)
                .filter_by(
                    electorate=tally_data.get("electorate"),
                    booth_name=result["booth_name"] or tally_data.get("booth_name"),
                )
                .first()
            )

            if existing_result:
                # Update existing result
                existing_result.image_url = image_url
                existing_result.data = data_json
                existing_result.timestamp = datetime.now(timezone.utc)
                existing_result.is_reviewed = 0  # Reset review status
                existing_result.reviewer = None
                db_result = existing_result
                logger.info(f"Updated existing result with ID: {db_result.id}")
            else:
                # Create new result
                db_result = Result(
                    image_url=image_url,
                    electorate=tally_data.get("electorate"),
                    booth_name=result["booth_name"] or tally_data.get("booth_name"),
                    data=data_json,
                )
                db.add(db_result)
                logger.info(f"Created new result with ID: {db_result.id}")

            db.commit()
            db.refresh(db_result)
            logger.info(f"Saved SMS result to database with ID: {db_result.id}")

            # Notify Flask app
            try:
                logger.info(f"Notifying Flask app at {FLASK_APP_URL}")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        FLASK_APP_URL,
                        json={
                            "result_id": db_result.id,
                            "timestamp": db_result.timestamp.isoformat(),
                            "electorate": tally_data.get("electorate"),
                            "booth_name": result["booth_name"]
                            or tally_data.get("booth_name"),
                        },
                    )
                    logger.info(
                        f"Flask app notification response: {response.status_code}"
                    )
            except Exception as notify_err:
                logger.error(f"Failed to notify Flask app: {notify_err}")

            return {
                "status": "success",
                "result_id": db_result.id,
                "electorate": tally_data.get("electorate"),
                "booth_name": result["booth_name"] or tally_data.get("booth_name"),
                "primary_votes": tally_data.get("primary_votes"),
                "two_candidate_preferred": tally_data.get("two_candidate_preferred"),
                "totals": tally_data.get("totals"),
            }
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing SMS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/load-reference-data")
async def load_reference_data():
    """
    Master admin endpoint to load all reference data (candidates, polling booths, 2022 results)
    """
    try:
        logger.info("Loading all reference data...")

        import sys
        import os
        from pathlib import Path
        from sqlalchemy import text

        # Get the parent directory of the current file's directory
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            logger.info(f"Adding parent directory to Python path: {parent_dir}")
            sys.path.append(parent_dir)

        logger.info(f"Current directory: {os.getcwd()}")
        logger.info(f"Parent directory: {parent_dir}")
        logger.info(f"Files in parent directory: {os.listdir(parent_dir)}")

        if os.path.exists("/.dockerenv"):
            import shutil

            utils_src = os.path.join(parent_dir, "utils")
            utils_dest = os.path.join(os.getcwd(), "utils")
            if os.path.exists(utils_src) and not os.path.exists(utils_dest):
                logger.info(f"Copying utils module from {utils_src} to {utils_dest}")
                shutil.copytree(utils_src, utils_dest)

        try:
            try:
                from utils.aec_data_downloader import download_and_process_aec_data
                from utils.booth_results_processor import (
                    process_and_load_booth_results,
                    process_and_load_polling_places,
                )
            except ImportError:
                sys.path.insert(0, os.path.join(parent_dir, "utils"))
                from aec_data_downloader import download_and_process_aec_data
                from booth_results_processor import (
                    process_and_load_booth_results,
                    process_and_load_polling_places,
                )

            # Load candidate data
            logger.info("Loading candidate data...")
            candidates_result = download_and_process_aec_data()

            # Load booth results
            logger.info("Loading booth results...")
            booth_results = process_and_load_booth_results()

            # Get the current count of polling places
            logger.info("Getting polling places count...")
            db = SessionLocal()
            try:
                result = db.execute(text("SELECT COUNT(*) FROM polling_places"))
                polling_places_count = result.scalar() or 0
            finally:
                db.close()

            return {
                "status": "success",
                "message": "Reference data loaded successfully",
                "details": {
                    "candidates_loaded": candidates_result,
                    "booth_results_loaded": booth_results,
                    "polling_places_loaded": True,
                    "polling_places_count": polling_places_count,
                },
            }
        except ImportError as ie:
            logger.error(f"Import error: {ie}")
            logger.info(f"Current sys.path: {sys.path}")
            logger.info(f"Current working directory: {os.getcwd()}")
            logger.info(f"Directory contents: {os.listdir(parent_dir)}")
            raise HTTPException(status_code=500, detail=f"Import error: {str(ie)}")
    except Exception as e:
        logger.error(f"Error loading reference data: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/polling-places/{division}")
async def get_polling_places(division: str):
    """
    Get polling places for a specific division

    Args:
        division: Name of the division/electorate
    """
    try:
        import sys
        from pathlib import Path

        # Get the parent directory of the current file's directory
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            logger.info(f"Adding parent directory to Python path: {parent_dir}")
            sys.path.append(parent_dir)

        from utils.booth_results_processor import get_polling_places_for_division

        polling_places = get_polling_places_for_division(division)
        return {"status": "success", "booth_results": polling_places}
    except Exception as e:
        logger.error(f"Error getting polling places for division {division}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/booth-results")
async def get_booth_results(electorate: Optional[str] = None):
    """
    Get polling places for a specific electorate/division
    """
    try:
        import sys
        from pathlib import Path

        # Get the parent directory of the current file's directory
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            logger.info(f"Adding parent directory to Python path: {parent_dir}")
            sys.path.append(parent_dir)

        from utils.booth_results_processor import get_polling_places_for_division

        if not electorate:
            return {"status": "error", "message": "Electorate parameter is required"}

        polling_places = get_polling_places_for_division(electorate)
        logger.info(
            f"Retrieved {len(polling_places)} polling places for electorate {electorate}"
        )

        return {"status": "success", "booth_results": polling_places}
    except Exception as e:
        logger.error(f"Error getting booth results for electorate {electorate}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/reset-results")
async def reset_results(request: Request):
    """
    Reset results for testing purposes
    """
    try:
        data = await request.json()
        division = data.get("division")
        booth_name = data.get("booth_name")
        all_results = data.get("all_results", False)

        db = SessionLocal()
        try:
            if all_results:
                db.query(Result).delete()
                message = "All results have been reset"
            elif division and booth_name:
                db.query(Result).filter_by(
                    electorate=division, booth_name=booth_name
                ).delete()
                message = f"Results for {booth_name} in {division} have been reset"
            elif division:
                db.query(Result).filter_by(electorate=division).delete()
                message = f"Results for {division} have been reset"
            else:
                return {
                    "status": "error",
                    "message": "Please specify what results to reset",
                }

            db.commit()
            logger.info(message)

            return {"status": "success", "message": message}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error resetting results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/unreviewed-results/{division}")
async def get_unreviewed_results(division: str):
    """
    Get unreviewed results for a specific division
    """
    try:
        db = SessionLocal()
        try:
            results = db.query(Result).filter_by(electorate=division).all()
            unreviewed_results = [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat(),
                    "electorate": r.electorate,
                    "booth_name": r.booth_name,
                    "image_url": r.image_url,
                }
                for r in results
                if not (r.data and r.data.get("reviewed"))
            ]
            return {"status": "success", "unreviewed_results": unreviewed_results}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting unreviewed results for division {division}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/result/{result_id}")
async def get_result(result_id: int):
    """
    Get a specific result by ID
    """
    try:
        db = SessionLocal()
        try:
            result = db.query(Result).filter_by(id=result_id).first()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Result with ID {result_id} not found"
                )

            # Parse the JSON data
            result_data = json.loads(result.data) if result.data else {}

            # Extract primary votes
            primary_votes = result_data.get("primary_votes", {})

            # Extract TCP votes
            tcp_votes = result_data.get("two_candidate_preferred", {})

            # Extract totals
            totals = result_data.get("totals", {})

            # Get polling places for this electorate
            polling_places = []
            try:
                conn = sqlite3.connect(
                    SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
                )
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT polling_place_id, polling_place_name, address, status, wheelchair_access
                    FROM polling_places 
                    WHERE division_name = ? 
                    ORDER BY polling_place_name
                """,
                    (result.electorate,),
                )
                polling_places = [
                    dict(
                        zip(
                            ["id", "name", "address", "status", "wheelchair_access"],
                            row,
                        )
                    )
                    for row in cursor.fetchall()
                ]
                conn.close()
            except Exception as e:
                logger.error(f"Error getting polling places: {e}")

            return {
                "status": "success",
                "result": {
                    "id": result.id,
                    "timestamp": result.timestamp.isoformat(),
                    "electorate": result.electorate,
                    "booth_name": result.booth_name,
                    "image_url": result.image_url,
                    "data": {
                        "primary_votes": primary_votes,
                        "two_candidate_preferred": tcp_votes,
                        "totals": totals,
                    },
                    "polling_places": polling_places,
                },
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/review-result/{result_id}")
async def review_result(result_id: int, request: Request):
    """
    Review and approve/reject a result
    """
    try:
        data = await request.json()
        action = data.get("action")

        if action not in ["approve", "reject"]:
            raise HTTPException(
                status_code=400, detail="Action must be 'approve' or 'reject'"
            )

        db = SessionLocal()
        try:
            result = db.query(Result).filter_by(id=result_id).first()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Result with ID {result_id} not found"
                )

            # Parse the existing data JSON string
            result_data = json.loads(result.data) if result.data else {}

            # Update the review status
            result_data["reviewed"] = True
            result_data["approved"] = action == "approve"
            result_data["reviewed_at"] = datetime.now(timezone.utc).isoformat()

            # Convert back to JSON string
            result.data = json.dumps(result_data)
            result.is_reviewed = 1
            result.reviewer = (
                "Admin"  # You might want to get this from the request or session
            )

            db.commit()

            message = (
                "Result approved successfully"
                if action == "approve"
                else "Result rejected"
            )
            logger.info(f"{message} for result {result_id}")

            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        FLASK_APP_URL,
                        json={
                            "result_id": result.id,
                            "timestamp": result.timestamp.isoformat(),
                            "electorate": result.electorate,
                            "booth_name": result.booth_name,
                            "action": "review",
                            "approved": (action == "approve"),
                        },
                    )
            except Exception as e:
                logger.error(f"Failed to notify Flask app: {e}")

            return {"status": "success", "message": message}
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results")
async def api_results():
    """
    Get all results ordered by timestamp descending
    """
    try:
        db = SessionLocal()
        try:
            results = (
                db.query(Result)
                .filter_by(is_reviewed=1)
                .order_by(Result.timestamp.desc())
                .all()
            )
            return {
                "status": "success",
                "results": [
                    {
                        "id": r.id,
                        "timestamp": r.timestamp.isoformat(),
                        "electorate": r.electorate,
                        "booth_name": r.booth_name,
                        "image_url": r.image_url,
                        "data": r.data,
                    }
                    for r in results
                ],
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results/{result_id}")
async def api_result_detail(result_id: int):
    """
    Get a specific result by ID
    """
    try:
        db = SessionLocal()
        try:
            result = db.query(Result).filter_by(id=result_id).first()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Result with ID {result_id} not found"
                )

            # Parse the JSON data
            result_data = json.loads(result.data) if result.data else {}

            return {
                "status": "success",
                "result": {
                    "id": result.id,
                    "timestamp": result.timestamp.isoformat(),
                    "electorate": result.electorate,
                    "booth_name": result.booth_name,
                    "image_url": result.image_url,
                    "data": result_data,
                },
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results/electorate/{electorate}")
async def get_electorate_results(electorate: str):
    logger.info(f"Received request for results in electorate: {electorate}")
    try:
        # Connect to the database
        db = SessionLocal()
        logger.info("Connected to database")

        # Get all results for the electorate
        results = (
            db.query(Result)
            .filter(Result.electorate == electorate, Result.is_reviewed == 1)
            .order_by(Result.timestamp.desc())
            .all()
        )

        logger.info(
            f"Found {len(results)} reviewed results for electorate {electorate}"
        )

        # Process results
        primary_votes = {}
        tcp_votes = {}
        booth_results = []

        for result in results:
            try:
                result_data = json.loads(result.data) if result.data else {}
                logger.info(
                    f"Processing result for booth {result.booth_name}: {result_data}"
                )

                # Aggregate primary votes
                if "primary_votes" in result_data:
                    for candidate, votes in result_data["primary_votes"].items():
                        if candidate not in primary_votes:
                            primary_votes[candidate] = 0
                        primary_votes[candidate] += votes

                # Aggregate TCP votes
                if "two_candidate_preferred" in result_data:
                    for candidate, votes in result_data[
                        "two_candidate_preferred"
                    ].items():
                        if candidate not in tcp_votes:
                            tcp_votes[candidate] = 0
                        tcp_votes[candidate] += votes

                booth_results.append(
                    {
                        "id": result.id,
                        "booth_name": result.booth_name,
                        "timestamp": result.timestamp.isoformat(),
                        "image_url": result.image_url,
                        "primary_votes": result_data.get("primary_votes", {}),
                        "tcp_votes": result_data.get("two_candidate_preferred", {}),
                        "totals": result_data.get("totals", {}),
                    }
                )
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON for result {result.id}: {str(e)}")
                continue

        # Convert aggregated votes to arrays for the frontend
        primary_votes_array = [
            {"candidate": k, "votes": v} for k, v in primary_votes.items()
        ]
        tcp_votes_array = [{"candidate": k, "votes": v} for k, v in tcp_votes.items()]

        # Calculate percentages
        total_primary_votes = sum(primary_votes.values())
        if total_primary_votes > 0:
            for vote in primary_votes_array:
                vote["percentage"] = (vote["votes"] / total_primary_votes) * 100

        total_tcp_votes = sum(tcp_votes.values())
        if total_tcp_votes > 0:
            for vote in tcp_votes_array:
                vote["percentage"] = (vote["votes"] / total_tcp_votes) * 100

        logger.info(f"Successfully processed {len(booth_results)} booth results")

        return {
            "status": "success",
            "booth_count": len(booth_results),
            "total_booths": len(
                booth_results
            ),  # This should be updated with actual total booths
            "booth_results": booth_results,
            "primary_votes": primary_votes_array,
            "tcp_votes": tcp_votes_array,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting results for electorate {electorate}: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
