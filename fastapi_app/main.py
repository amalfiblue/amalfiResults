import os
import re
import sqlite3
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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
            # Store the image in a proper location and use a proper URL
            image_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            image_path = f"static/uploads/{image_filename}"
            os.makedirs("static/uploads", exist_ok=True)

            # Save the image file
            with open(image_path, "wb") as f:
                f.write(contents)

            # Use a proper URL path
            image_url = f"/static/uploads/{image_filename}"

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

            return {
                "status": "success",
                "result": {
                    "id": result.id,
                    "timestamp": result.timestamp.isoformat(),
                    "electorate": result.electorate,
                    "booth_name": result.booth_name,
                    "image_url": result.image_url,
                    "data": result.data,
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
async def api_results_by_electorate(electorate: str):
    """
    Get results for a specific electorate
    """
    try:
        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        logger.info(f"Connecting to database at: {db_path}")
        logger.info(f"Current working directory: {os.getcwd()}")

        if not os.path.exists(db_path):
            logger.error(f"Database file does not exist: {db_path}")
            return {"status": "error", "detail": f"Database file not found: {db_path}"}

        logger.info(f"Database file exists: {db_path}")
        logger.info(f"File permissions: {oct(os.stat(db_path).st_mode)}")
        logger.info(f"File owner: {os.stat(db_path).st_uid}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, timestamp, electorate, booth_name, image_url, data
            FROM results 
            WHERE electorate = ? AND is_reviewed = 1
            ORDER BY timestamp DESC
        """,
            (electorate,),
        )

        columns = ["id", "timestamp", "electorate", "booth_name", "image_url", "data"]
        results_data = []

        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result["data"] and isinstance(result["data"], str):
                try:
                    result["data"] = json.loads(result["data"])
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse JSON data for result {result['id']}"
                    )

            results_data.append(result)

        conn.close()

        return {"status": "success", "results": results_data}
    except Exception as e:
        logger.error(f"Error getting results for electorate {electorate}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results/count/{electorate}")
async def api_results_count(electorate: str):
    """
    Count results for a specific electorate
    """
    try:
        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM results WHERE electorate = ?", (electorate,)
        )
        count = cursor.fetchone()[0]
        conn.close()

        return {"status": "success", "count": count}
    except Exception as e:
        logger.error(f"Error counting results for electorate {electorate}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tcp-candidates/{electorate}")
async def api_tcp_candidates(electorate: str):
    """
    Get TCP candidates for a specific electorate
    """
    try:
        db = SessionLocal()
        try:
            candidates = db.query(TCPCandidate).filter_by(electorate=electorate).all()
            return {
                "status": "success",
                "candidates": [
                    {
                        "id": c.id,
                        "electorate": c.electorate,
                        "candidate_name": c.candidate_name,
                        "party": c.party,
                    }
                    for c in candidates
                ],
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting TCP candidates for electorate {electorate}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tcp-candidates/{electorate}")
async def api_update_tcp_candidates(electorate: str, request: Request):
    """
    Update TCP candidates for a specific electorate
    """
    try:
        data = await request.json()
        logger.info(f"Received TCP candidates update request: {data}")

        # Handle both formats: candidate_ids or candidates
        candidate_ids = data.get("candidate_ids", [])
        candidates_data = data.get("candidates", [])

        db = SessionLocal()
        try:
            # Delete existing TCP candidates for this electorate
            db.query(TCPCandidate).filter_by(electorate=electorate).delete()
            logger.info(f"Deleted existing TCP candidates for {electorate}")

            if candidate_ids and not candidates_data:
                logger.info(f"Looking up candidates by IDs: {candidate_ids}")

                db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Get candidate information for each ID
                for candidate_id in candidate_ids:
                    cursor.execute(
                        "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
                    )
                    candidate_row = cursor.fetchone()

                    if candidate_row:
                        columns = [col[0] for col in cursor.description]
                        candidate = dict(zip(columns, candidate_row))

                        logger.info(f"Found candidate: {candidate}")

                        tcp_candidate = TCPCandidate(
                            electorate=electorate,
                            candidate_name=candidate.get("candidate_name"),
                            party=candidate.get("party"),
                        )
                        db.add(tcp_candidate)
                        logger.info(
                            f"Added TCP candidate: {candidate.get('candidate_name')}"
                        )

                conn.close()
            else:
                # Add new TCP candidates from candidates_data
                for candidate in candidates_data:
                    tcp_candidate = TCPCandidate(
                        electorate=electorate,
                        candidate_name=candidate.get("candidate_name"),
                        party=candidate.get("party"),
                    )
                    db.add(tcp_candidate)
                    logger.info(
                        f"Added TCP candidate: {candidate.get('candidate_name')}"
                    )

            db.commit()
            logger.info(f"Committed TCP candidates for {electorate}")

            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        FLASK_APP_URL,
                        json={"electorate": electorate, "action": "tcp_update"},
                    )
                    logger.info(f"Notified Flask app about TCP update for {electorate}")
            except Exception as e:
                logger.error(f"Failed to notify Flask app: {e}")

            return {
                "status": "success",
                "message": "TCP candidates updated successfully",
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating TCP candidates: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error updating TCP candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/electorates")
async def api_electorates():
    """
    Get all unique electorates from the candidates table
    """
    try:
        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT electorate FROM candidates ORDER BY electorate")
        electorates = [row[0] for row in cursor.fetchall()]
        conn.close()

        return {"status": "success", "electorates": electorates}
    except Exception as e:
        logger.error(f"Error getting electorates: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/candidates")
async def api_candidates(electorate: str = None, house: str = "house"):
    """
    Get all candidates or filter by electorate and house
    """
    try:
        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        logger.info(f"Connecting to database at: {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM candidates"
        params = []

        if electorate:
            query += " WHERE electorate = ?"
            params.append(electorate)

            if house:
                query += " AND candidate_type = ?"
                params.append(house)

        query += " ORDER BY ballot_position"

        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        candidates = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()

        return {"status": "success", "candidates": candidates}
    except Exception as e:
        logger.error(f"Error getting candidates: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/candidates/{electorate}")
async def api_candidates_by_electorate(electorate: str, candidate_type: str = "house"):
    """
    Get candidates for a specific electorate
    """
    try:
        conn = sqlite3.connect(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", ""))
        cursor = conn.cursor()

        logger.info(
            f"Filtering candidates for electorate: {electorate}, candidate_type: {candidate_type}"
        )

        # Use electorate column for both senate and house candidates
        if candidate_type.lower() == "senate":
            cursor.execute(
                "SELECT * FROM candidates WHERE electorate = ? AND candidate_type = 'senate' ORDER BY ballot_position",
                (electorate,),
            )
        else:
            cursor.execute(
                "SELECT * FROM candidates WHERE electorate = ? AND candidate_type = 'house' ORDER BY ballot_position",
                (electorate,),
            )

        columns = [col[0] for col in cursor.description]
        candidates = [dict(zip(columns, row)) for row in cursor.fetchall()]

        logger.info(f"Found {len(candidates)} candidates matching the criteria")
        conn.close()

        return {"status": "success", "candidates": candidates}
    except Exception as e:
        logger.error(f"Error getting candidates for electorate {electorate}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/{electorate}")
async def api_dashboard(electorate: str):
    """
    Get all dashboard data for a specific electorate
    """
    try:
        logger.info(f"=== Starting dashboard request for electorate: {electorate} ===")
        import sys
        import os
        from pathlib import Path

        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        logger.info(f"Connecting to database at: {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Log all results for this electorate before filtering
        cursor.execute(
            """
            SELECT id, timestamp, electorate, booth_name, is_reviewed
            FROM results 
            WHERE electorate = ?
            ORDER BY timestamp DESC
        """,
            (electorate,),
        )
        all_electorate_results = cursor.fetchall()
        logger.info(
            f"Found {len(all_electorate_results)} total results for {electorate}:"
        )
        for result in all_electorate_results:
            logger.info(
                f"Result ID: {result[0]}, Booth: {result[3]}, Reviewed: {result[4]}"
            )

        # Get reviewed results count
        cursor.execute(
            "SELECT COUNT(*) FROM results WHERE electorate = ? AND is_reviewed = 1",
            (electorate,),
        )
        reviewed_count = cursor.fetchone()[0]
        logger.info(f"Found {reviewed_count} reviewed results for {electorate}")

        # Get results with data
        cursor.execute(
            """
            SELECT id, timestamp, electorate, booth_name, image_url, data
            FROM results 
            WHERE electorate = ? AND is_reviewed = 1
            ORDER BY timestamp DESC
        """,
            (electorate,),
        )

        columns = ["id", "timestamp", "electorate", "booth_name", "image_url", "data"]
        results = []

        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result["data"] and isinstance(result["data"], str):
                try:
                    result["data"] = json.loads(result["data"])
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse JSON data for result {result['id']}"
                    )

            results.append(result)
            logger.info(f"Processing result for booth: {result['booth_name']}")

        logger.info(f"Total processed results: {len(results)}")

        booth_count = reviewed_count
        total_booths = len(results)
        completion_percentage = (
            (booth_count / total_booths * 100) if total_booths > 0 else 0
        )

        booth_results = []
        primary_votes = {}

        for result in results:
            booth_data = {
                "id": result["id"],
                "timestamp": result["timestamp"],
                "booth_name": result["booth_name"],
                "image_url": result["image_url"],
            }

            if result["data"] and "primary_votes" in result["data"]:
                booth_data["primary_votes"] = result["data"]["primary_votes"]

                for candidate, votes in result["data"]["primary_votes"].items():
                    if candidate not in primary_votes:
                        primary_votes[candidate] = {"votes": 0, "percentage": 0}
                    primary_votes[candidate]["votes"] += votes

            if result["data"] and "tcp_votes" in result["data"]:
                booth_data["tcp_votes"] = result["data"]["tcp_votes"]

            if result["data"] and "totals" in result["data"]:
                booth_data["totals"] = result["data"]["totals"]

            booth_results.append(booth_data)

        total_primary_votes = sum(
            candidate["votes"] for candidate in primary_votes.values()
        )
        if total_primary_votes > 0:
            for candidate in primary_votes:
                primary_votes[candidate]["percentage"] = (
                    primary_votes[candidate]["votes"] / total_primary_votes
                ) * 100

        # Get TCP candidates
        cursor.execute(
            """
            SELECT id, electorate, candidate_name
            FROM tcp_candidates
            WHERE electorate = ?
        """,
            (electorate,),
        )

        tcp_candidates_data = []
        tcp_candidate_names = []

        for row in cursor.fetchall():
            tcp_candidate = {
                "id": row[0],
                "electorate": row[1],
                "candidate_name": row[2],
            }
            tcp_candidates_data.append(tcp_candidate)
            tcp_candidate_names.append(row[2])  # candidate_name

        tcp_votes = {}
        for tcp_candidate in tcp_candidate_names:
            tcp_votes[tcp_candidate] = 0

        for result in results:
            if result["data"] and "tcp_votes" in result["data"]:
                for tcp_candidate, votes in result["data"]["tcp_votes"].items():
                    if tcp_candidate in tcp_votes:
                        tcp_votes[tcp_candidate] += votes

        tcp_votes_array = []
        total_tcp_votes = sum(tcp_votes.values())

        for candidate, votes in tcp_votes.items():
            percentage = (votes / total_tcp_votes * 100) if total_tcp_votes > 0 else 0
            tcp_votes_array.append(
                {"candidate": candidate, "votes": votes, "percentage": percentage}
            )

        primary_votes_array = []
        for candidate, data in primary_votes.items():
            primary_votes_array.append(
                {
                    "candidate": candidate,
                    "votes": data["votes"],
                    "percentage": data["percentage"],
                }
            )

        conn.close()

        return {
            "status": "success",
            "booth_count": booth_count,
            "total_booths": total_booths,
            "completion_percentage": completion_percentage,
            "booth_results": booth_results,
            "primary_votes": primary_votes_array,
            "tcp_candidates": tcp_candidates_data,
            "tcp_votes": tcp_votes_array,
        }
    except Exception as e:
        logger.error(f"Error getting dashboard data for electorate {electorate}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/{electorate}/candidate-votes")
@app.get("/api/dashboard/{electorate}/candidate-votes")
async def api_candidate_votes(electorate: str):
    """
    Get candidate votes for a specific electorate
    """
    try:
        db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
        logger.info(f"Connecting to database at: {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get candidates for this electorate
        cursor.execute(
            "SELECT * FROM candidates WHERE electorate = ? ORDER BY ballot_position",
            (electorate,),
        )
        columns = [col[0] for col in cursor.description]
        candidates = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Get results for this electorate
        cursor.execute(
            """
            SELECT id, timestamp, electorate, booth_name, data
            FROM results 
            WHERE electorate = ? 
            ORDER BY timestamp DESC
        """,
            (electorate,),
        )

        columns = ["id", "timestamp", "electorate", "booth_name", "data"]
        results = []

        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result["data"] and isinstance(result["data"], str):
                try:
                    result["data"] = json.loads(result["data"])
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse JSON data for result {result['id']}"
                    )

            results.append(result)

        primary_votes = {}
        for candidate in candidates:
            primary_votes[candidate["candidate_name"]] = {
                "votes": 0,
                "percentage": 0,
                "party": candidate["party"],
            }

        for result in results:
            if result["data"] and "primary_votes" in result["data"]:
                for candidate, votes in result["data"]["primary_votes"].items():
                    if candidate in primary_votes:
                        primary_votes[candidate]["votes"] += votes

        total_primary_votes = sum(
            candidate_data["votes"] for candidate_data in primary_votes.values()
        )
        if total_primary_votes > 0:
            for candidate in primary_votes:
                primary_votes[candidate]["percentage"] = (
                    primary_votes[candidate]["votes"] / total_primary_votes
                ) * 100

        primary_votes_array = []
        for candidate, data in primary_votes.items():
            primary_votes_array.append(
                {
                    "candidate": candidate,
                    "votes": data["votes"],
                    "percentage": data["percentage"],
                    "party": data["party"],
                }
            )

        conn.close()

        return {
            "status": "success",
            "candidates": candidates,
            "primary_votes": primary_votes_array,
        }
    except Exception as e:
        logger.error(f"Error getting candidate votes for electorate {electorate}: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/manual-entry")
async def manual_entry(request: Request):
    """
    Handle manual entry of booth results when image scanning fails
    """
    try:
        data = await request.json()
        logger.info(f"Received manual entry request: {data}")

        result_id = data.get("result_id")
        booth_name = data.get("booth_name")
        electorate = data.get("electorate")
        primary_votes = data.get("primary_votes", {})
        two_candidate_preferred = data.get("two_candidate_preferred", {})
        totals = data.get("totals", {})

        if not booth_name or not electorate:
            raise HTTPException(
                status_code=400, detail="Booth name and electorate are required"
            )

        data_json = json.dumps(
            {
                "primary_votes": primary_votes,
                "two_candidate_preferred": two_candidate_preferred,
                "totals": totals,
                "manual_entry": True,
            }
        )

        db = SessionLocal()
        try:
            if result_id:
                existing_result = (
                    db.query(Result).filter(Result.id == result_id).first()
                )
                if existing_result:
                    existing_result.data = data_json
                    db.commit()
                    logger.info(f"Updated existing result with ID: {result_id}")
                    result_id = existing_result.id
                else:
                    # Create new result if ID not found
                    db_result = Result(
                        booth_name=booth_name,
                        electorate=electorate,
                        data=data_json,
                        is_reviewed=1,  # Mark as reviewed since manually entered
                        reviewer="Manual Entry",
                    )
                    db.add(db_result)
                    db.commit()
                    db.refresh(db_result)
                    result_id = db_result.id
                    logger.info(f"Created new result with ID: {result_id}")
            else:
                db_result = Result(
                    booth_name=booth_name,
                    electorate=electorate,
                    data=data_json,
                    is_reviewed=1,  # Mark as reviewed since manually entered
                    reviewer="Manual Entry",
                )
                db.add(db_result)
                db.commit()
                db.refresh(db_result)
                result_id = db_result.id
                logger.info(f"Created new result with ID: {result_id}")

            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        FLASK_APP_URL,
                        json={
                            "result_id": result_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "electorate": electorate,
                            "booth_name": booth_name,
                            "action": "manual_entry",
                        },
                    )
                    logger.info(
                        f"Notified Flask app about manual entry for {booth_name}"
                    )
            except Exception as e:
                logger.error(f"Failed to notify Flask app: {e}")

            return {
                "status": "success",
                "result_id": result_id,
                "message": "Manual result entry successful",
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing manual entry: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing manual entry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results/{electorate}")
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
                result_data = json.loads(result.data)
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
                        "booth_name": result.booth_name,
                        "data": result_data,
                        "timestamp": result.timestamp.isoformat(),
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

        logger.info(f"Successfully processed {len(booth_results)} booth results")

        return {
            "status": "success",
            "primary_votes": primary_votes_array,
            "tcp_votes": tcp_votes_array,
            "booth_count": len(booth_results),
            "total_booths": len(
                booth_results
            ),  # This should be updated with actual total booths
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
