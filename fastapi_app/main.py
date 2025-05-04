import os
import re
import sqlite3
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
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
from collections import defaultdict
import urllib.parse

# Add the parent directory to Python path to find modules
import sys

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from common.image_processor import ImageProcessor
from common.db_utils import get_sqlalchemy_url, ensure_database_exists
from common.booth_results_processor import (
    process_and_load_booth_results,
    create_polling_places_table,
    get_polling_places_for_division,
)
from common.candidate_data_loader import process_and_load_candidate_data

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
SQLALCHEMY_DATABASE_URL = get_sqlalchemy_url()
logger.info(f"Running in {'Docker' if is_docker else 'local'} environment")
logger.info(f"Using database path: {SQLALCHEMY_DATABASE_URL}")
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

# Initialize database
ensure_database_exists()
SQLALCHEMY_DATABASE_URL = get_sqlalchemy_url()

# Debug logging
logger.error(
    f"ABSOLUTE DB PATH: {os.path.abspath(SQLALCHEMY_DATABASE_URL.replace('sqlite:////', ''))}"
)
logger.error(f"DB URL BEING USED: {SQLALCHEMY_DATABASE_URL}")
logger.error(f"CURRENT WORKING DIR: {os.getcwd()}")

# Create database engine and session
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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
    aec_booth_name = Column(
        String, nullable=True
    )  # Optional until migration is complete


class PollingPlace(Base):
    __tablename__ = "polling_places"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String, nullable=False)
    division_id = Column(Integer, nullable=False)
    division_name = Column(String, nullable=False)
    polling_place_id = Column(Integer, nullable=False)
    polling_place_name = Column(String, nullable=False)
    address = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    status = Column(String)
    wheelchair_access = Column(String)
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


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    candidate_name = Column(String, index=True)
    party = Column(String)
    electorate = Column(String, index=True)
    ballot_position = Column(Integer)
    candidate_type = Column(String)
    state = Column(String)
    data = Column(String)  # JSON data as string


# Create database tables
Base.metadata.create_all(bind=engine)

# Create polling places table
create_polling_places_table()

# Initialize image processor
image_processor = ImageProcessor()


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
        nums = [int(x) for x in row if x.isdigit()]

        if "TOTAL FORMAL" in row_text and nums:
            result["totals"]["formal"] = nums[0]
        elif "INFORMAL" in row_text and nums:
            result["totals"]["informal"] = nums[0]
        elif "TOTAL VOTES" in row_text and nums:
            result["totals"]["total"] = nums[0]

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
async def inbound_sms(
    request: Request,
    from_number: str = Form(..., alias="from"),
    to_number: str = Form(..., alias="to"),
    body: str = Form(...),
    timestamp: str = Form(...),
    media: str = Form(None),
):
    logger.info(f"Received SMS from {from_number} to {to_number} at {timestamp}")
    logger.info(f"Message body: {body}")
    logger.info(f"Media URL: {media}")

    # Determine the image URL
    image_url = media
    if not image_url:
        # Extract URL from message body if no media parameter
        url_match = re.search(r"https?://[^\s]+", body)
        if url_match:
            image_url = url_match.group(0)
            logger.info(f"Extracted URL from message body: {image_url}")
        else:
            logger.error("No image URL found in message")
            raise HTTPException(status_code=400, detail="No image URL found in message")

    try:
        # For AWS S3 URLs, we need to preserve the exact URL structure
        if (
            "s3.amazonaws.com" in image_url
            or "s3.ap-southeast-2.amazonaws.com" in image_url
        ):
            # Clean the URL by removing any non-printable characters but preserve the structure
            cleaned_url = "".join(c for c in image_url if c.isprintable())
            logger.info(f"Using cleaned S3 URL: {cleaned_url}")

            # Download the image
            async with httpx.AsyncClient() as client:
                response = await client.get(cleaned_url)
                response.raise_for_status()
                image_data = response.content
        else:
            # For non-S3 URLs, we can use standard URL parsing
            parsed_url = urllib.parse.urlparse(image_url)
            encoded_url = urllib.parse.urlunparse(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    parsed_url.query,
                    parsed_url.fragment,
                )
            )
            logger.info(f"Using encoded URL: {encoded_url}")

            # Download the image
            async with httpx.AsyncClient() as client:
                response = await client.get(encoded_url)
                response.raise_for_status()
                image_data = response.content

        # Process the image
        result = await image_processor.process_sms_image(image_url)

        # Save to database
        result_id = save_to_database(result)

        return {"status": "success", "result_id": result_id}
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
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
                from common.aec_data_downloader import download_and_process_aec_data
                from common.booth_results_processor import (
                    process_and_load_booth_results,
                    process_and_load_polling_places,
                )
            except ImportError:
                sys.path.insert(0, os.path.join(parent_dir, "common"))
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


@app.get("/admin/polling-places/division/{division}")
async def get_admin_polling_places(division: str):
    """
    Get polling places for a specific division (admin endpoint)
    """
    try:
        import sys
        from pathlib import Path

        # Get the parent directory of the current file's directory
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            logger.info(f"Adding parent directory to Python path: {parent_dir}")
            sys.path.append(parent_dir)

        from common.booth_results_processor import get_polling_places_for_division

        polling_places = get_polling_places_for_division(division)
        logger.info(
            f"Retrieved {len(polling_places)} polling places for division {division}"
        )

        return {
            "status": "success",
            "polling_places": [
                {
                    "id": p["id"],
                    "polling_place_id": p["polling_place_id"],
                    "polling_place_name": p["polling_place_name"],
                    "address": p["address"],
                    "status": p["status"],
                    "wheelchair_access": p["wheelchair_access"],
                    "data": json.loads(p["data"]) if p["data"] else {},
                }
                for p in polling_places
            ],
        }
    except Exception as e:
        logger.error(f"Error getting polling places for division {division}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/booth-results")
async def get_booth_results(
    division: Optional[str] = None,
    electorate: Optional[str] = None,
    booth: Optional[str] = None,
):
    """
    Get polling places for a specific division/booth with TCP results between the actual TCP candidates
    """
    try:
        import sys
        from pathlib import Path

        # Get the parent directory of the current file's directory
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            logger.info(f"Adding parent directory to Python path: {parent_dir}")
            sys.path.append(parent_dir)

        from common.booth_results_processor import get_polling_places_for_division

        # Use either division or electorate parameter
        division_name = division or electorate
        if not division_name:
            return {
                "status": "error",
                "message": "Division/electorate parameter is required",
            }

        # Get polling places
        polling_places = get_polling_places_for_division(division_name)
        logger.info(
            f"Retrieved {len(polling_places)} polling places for division {division_name}"
        )

        # Filter by booth if specified
        if booth:
            polling_places = [
                p for p in polling_places if p["polling_place_name"] == booth
            ]

        # Get TCP candidates for this division
        db = SessionLocal()
        try:
            # Get current TCP candidates
            tcp_candidates = (
                db.query(TCPCandidate).filter_by(electorate=division_name).all()
            )

            # Get candidate names, defaulting to generic terms if not set
            tcp_candidate_1_name = "TCP Candidate 1"
            tcp_candidate_2_name = "TCP Candidate 2"

            if len(tcp_candidates) >= 2:
                tcp_candidate_1_name = tcp_candidates[0].candidate_name
                tcp_candidate_2_name = tcp_candidates[1].candidate_name
            elif len(tcp_candidates) == 1:
                tcp_candidate_1_name = tcp_candidates[0].candidate_name

            # Get results for this division
            results = db.query(Result).filter_by(electorate=division_name).all()

            # Create a mapping of booth names to results
            results_map = {}
            for result in results:
                if result.aec_booth_name:
                    booth_name = result.aec_booth_name.upper()
                elif result.booth_name:
                    booth_name = result.booth_name.upper()
                else:
                    continue

                # Parse the result data
                result_data = json.loads(result.data) if result.data else {}
                tcp_data = result_data.get("two_candidate_preferred", {})

                # Get TCP percentages
                tcp_candidate_1_percentage = None
                tcp_candidate_2_percentage = None

                if tcp_data and len(tcp_candidates) >= 2:
                    tcp1_name = tcp_candidates[0].candidate_name
                    tcp2_name = tcp_candidates[1].candidate_name

                    if tcp1_name in tcp_data and tcp2_name in tcp_data:
                        tcp1_votes = sum(tcp_data[tcp1_name].values())
                        tcp2_votes = sum(tcp_data[tcp2_name].values())
                        total_votes = tcp1_votes + tcp2_votes

                        if total_votes > 0:
                            tcp_candidate_1_percentage = (
                                tcp1_votes / total_votes
                            ) * 100
                            tcp_candidate_2_percentage = (
                                tcp2_votes / total_votes
                            ) * 100

                results_map[booth_name] = {
                    "tcp_candidate_1_percentage": tcp_candidate_1_percentage,
                    "tcp_candidate_2_percentage": tcp_candidate_2_percentage,
                    "swing": None,  # We'll calculate this later
                    "is_reviewed": result.is_reviewed,
                    "result_id": result.id,
                }

            # Get 2022 results for swing calculation
            cursor = db.execute(
                text(
                    """
                SELECT polling_place_name, 
                       liberal_national_percentage
                FROM booth_results_2022
                WHERE division_name = :electorate
            """
                ),
                {"electorate": division_name},
            )
            results_2022 = {
                row[0]: {
                    "tcp1_name": tcp_candidate_1_name,
                    "tcp2_name": tcp_candidate_2_name,
                    "tcp1_pct": 100
                    - row[1],  # TCP1 percentage is 100 - Liberal National percentage
                    "tcp2_pct": row[1],  # TCP2 is Liberal National percentage
                }
                for row in cursor.fetchall()
            }
        finally:
            db.close()

        return {
            "status": "success",
            "tcp_candidate_1_name": tcp_candidate_1_name,
            "tcp_candidate_2_name": tcp_candidate_2_name,
            "results_map": results_map,
            "booth_results": [
                {
                    "id": p["id"],
                    "polling_place_id": p["polling_place_id"],
                    "polling_place_name": p["polling_place_name"],
                    "address": p["address"],
                    "status": p["status"],
                    "wheelchair_access": p["wheelchair_access"],
                    "data": json.loads(p["data"]) if p["data"] else {},
                    # TCP data
                    "tcp_candidate_1_percentage": None,
                    "tcp_candidate_2_percentage": None,
                    "is_reviewed": 0,
                    # 2022 TCP data
                    "tcp_2022": results_2022.get(p["polling_place_name"], None),
                    "swing": None,
                }
                for p in polling_places
            ],
        }
    except Exception as e:
        logger.error(f"Error getting booth results for division {division_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def calculate_tcp_swing(
    current_tcp1, current_tcp2, current_tcp1_name, current_tcp2_name, previous_result
):
    """
    Calculate the swing between current and previous TCP results.
    Takes into account that TCP candidates might be in different orders between years,
    and handles cases where we can compare Liberal candidate performance even when
    the independent candidate has changed.
    Returns the swing percentage (positive means swing to current TCP candidate 1)
    """
    if (
        not current_tcp1
        or not current_tcp2
        or not previous_result
        or not current_tcp1_name
        or not current_tcp2_name
    ):
        return None

    prev = previous_result

    # First try to match candidates by name
    current_liberal = None
    prev_liberal = None

    # Find which current candidate is Liberal
    if "LIBERAL" in current_tcp1_name.upper():
        current_liberal = {"name": current_tcp1_name, "pct": current_tcp1}
    elif "LIBERAL" in current_tcp2_name.upper():
        current_liberal = {"name": current_tcp2_name, "pct": current_tcp2}

    # Find which previous candidate was Liberal
    if "LIBERAL" in prev["tcp1_name"].upper():
        prev_liberal = {"name": prev["tcp1_name"], "pct": prev["tcp1_pct"]}
    elif "LIBERAL" in prev["tcp2_name"].upper():
        prev_liberal = {"name": prev["tcp2_name"], "pct": prev["tcp2_pct"]}

    # If we have both Liberal candidates, calculate swing based on their performance
    if current_liberal and prev_liberal:
        # Calculate swing to Liberal (positive means swing to Liberal)
        swing = current_liberal["pct"] - prev_liberal["pct"]
        return round(swing, 2)

    # If we can't match by Liberal party, try matching by candidate names
    if (
        prev["tcp1_name"] == current_tcp2_name
        and prev["tcp2_name"] == current_tcp1_name
    ):
        # Candidates are in opposite order, flip the previous results
        prev_tcp1 = prev["tcp2_pct"]
        prev_tcp2 = prev["tcp1_pct"]
    else:
        # Candidates are in same order (or different candidates)
        prev_tcp1 = prev["tcp1_pct"]
        prev_tcp2 = prev["tcp2_pct"]

    # Calculate the swing
    swing = ((current_tcp1 - prev_tcp1) - (current_tcp2 - prev_tcp2)) / 2

    return round(swing, 2)


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


@app.get("/admin/unreviewed-results/division/{division}")
async def get_unreviewed_results(division: str):
    """
    Get unreviewed results for a specific division
    """
    try:
        db = SessionLocal()
        try:
            # Get all results for the division that haven't been reviewed
            results = (
                db.query(Result)
                .filter(
                    Result.electorate == division,
                    Result.is_reviewed == 0,  # Only get unreviewed results
                )
                .all()
            )

            unreviewed_results = [
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat(),
                    "electorate": r.electorate,
                    "booth_name": r.booth_name,
                    "image_url": r.image_url,
                }
                for r in results
            ]

            logger.info(
                f"Found {len(unreviewed_results)} unreviewed results for division {division}"
            )
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

            # Get candidates with ballot positions
            candidates = (
                db.query(Candidate).filter_by(electorate=result.electorate).all()
            )
            candidate_positions = {
                c.candidate_name: c.ballot_position for c in candidates
            }

            # Sort primary votes by ballot position
            sorted_primary_votes = {}
            for candidate in sorted(
                primary_votes.keys(), key=lambda x: candidate_positions.get(x, 999)
            ):
                sorted_primary_votes[candidate] = primary_votes[candidate]

            # Extract TCP votes
            tcp_votes = result_data.get("two_candidate_preferred", {})

            # Sort TCP votes by ballot position
            sorted_tcp_votes = {}
            for tcp_candidate in tcp_votes:
                sorted_tcp_votes[tcp_candidate] = {}
                for candidate in sorted(
                    tcp_votes[tcp_candidate].keys(),
                    key=lambda x: candidate_positions.get(x, 999),
                ):
                    sorted_tcp_votes[tcp_candidate][candidate] = tcp_votes[
                        tcp_candidate
                    ][candidate]

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
                        "primary_votes": sorted_primary_votes,
                        "two_candidate_preferred": sorted_tcp_votes,
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
        booth_name = data.get("booth_name")  # Get the booth name from the request
        primary_votes = data.get("primary_votes")  # Get edited primary votes
        tcp_votes = data.get("tcp_votes")  # Get edited TCP votes
        totals = data.get("totals")  # Get edited totals

        if action not in ["approve", "reject"]:
            raise HTTPException(
                status_code=400, detail="Action must be 'approve' or 'reject'"
            )

        if not booth_name:
            raise HTTPException(status_code=400, detail="Booth name is required")

        db = SessionLocal()
        try:
            result = db.query(Result).filter_by(id=result_id).first()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Result with ID {result_id} not found"
                )

            # Parse the existing data JSON string
            result_data = json.loads(result.data) if result.data else {}

            # Update the data with edited values if provided
            if primary_votes is not None:
                result_data["primary_votes"] = primary_votes
            if tcp_votes is not None:
                result_data["two_candidate_preferred"] = tcp_votes
            if totals is not None:
                result_data["totals"] = totals

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
            result.booth_name = booth_name  # Update the booth name
            result.aec_booth_name = booth_name  # Also update the AEC booth name

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
                            "booth_name": result.aec_booth_name,  # Use AEC booth name in notification
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


@app.get("/results/division/{division}")
async def get_division_results(division: str):
    logger.info(f"Received request for results in division: {division}")
    try:
        # Connect to the database
        db = SessionLocal()
        logger.info("Connected to database")

        # Get all results for the division
        results = (
            db.query(Result)
            .filter(Result.electorate == division, Result.is_reviewed == 1)
            .order_by(Result.timestamp.desc())
            .all()
        )

        logger.info(f"Found {len(results)} reviewed results for division {division}")

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
                    for tcp_candidate, candidate_votes in result_data[
                        "two_candidate_preferred"
                    ].items():
                        for candidate, votes in candidate_votes.items():
                            if candidate not in tcp_votes:
                                tcp_votes[candidate] = {}
                            if tcp_candidate not in tcp_votes[candidate]:
                                tcp_votes[candidate][tcp_candidate] = 0
                            tcp_votes[candidate][tcp_candidate] += votes

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

        # Convert TCP votes to array format
        tcp_votes_array = []
        tcp_candidates = set()

        # First, collect all TCP candidates
        for candidate_votes in tcp_votes.values():
            tcp_candidates.update(candidate_votes.keys())

        # Convert to list and sort
        tcp_candidates = sorted(list(tcp_candidates))

        # Create array with vote distributions
        for candidate, tcp_distribution in tcp_votes.items():
            # Skip TCP candidates themselves
            if candidate in tcp_candidates:
                continue

            entry = {
                "candidate": candidate,
                "primary_votes": primary_votes.get(candidate, 0),
                "distributions": {},
            }

            # Add distribution to each TCP candidate
            for tcp_candidate in tcp_candidates:
                entry["distributions"][tcp_candidate] = tcp_distribution.get(
                    tcp_candidate, 0
                )

            tcp_votes_array.append(entry)

        # Calculate percentages
        total_primary_votes = sum(primary_votes.values())
        if total_primary_votes > 0:
            for vote in primary_votes_array:
                vote["percentage"] = (vote["votes"] / total_primary_votes) * 100

        # Calculate TCP percentages
        for entry in tcp_votes_array:
            total = entry["primary_votes"]
            if total > 0:
                for tcp_candidate, votes in entry["distributions"].items():
                    entry["distributions"][tcp_candidate] = {
                        "votes": votes,
                        "percentage": (votes / total) * 100,
                    }

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
        logger.error(f"Error getting results for division {division}: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
        logger.info("Database connection closed")


@app.get("/electorates")
async def get_electorates():
    """
    Get all unique electorates/divisions from the database
    """
    try:
        db = SessionLocal()
        try:
            # Get unique divisions from polling places table using simple distinct
            polling_divisions = db.query(PollingPlace.division_name).distinct().all()
            divisions = [d[0] for d in polling_divisions if d[0]]

            # Get unique electorates from results table
            result_electorates = db.query(Result.electorate).distinct().all()
            electorates = [e[0] for e in result_electorates if e[0]]

            # Combine and deduplicate
            all_electorates = list(set(divisions + electorates))
            all_electorates.sort()

            return {"status": "success", "electorates": all_electorates}
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting electorates: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/tcp-candidates/division/{division}")
async def get_tcp_candidates(division: str):
    """
    Get TCP candidates for a specific division
    """
    try:
        db = SessionLocal()
        try:
            candidates = db.query(TCPCandidate).filter_by(electorate=division).all()
            return {
                "status": "success",
                "candidates": [
                    {"id": c.id, "candidate_name": c.candidate_name, "party": c.party}
                    for c in candidates
                ],
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting TCP candidates for {division}: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/tcp-candidates/division/{division}")
async def set_tcp_candidates(division: str, request: Request):
    """
    Set TCP candidates for a specific division
    """
    try:
        data = await request.json()
        candidate_ids = data.get("candidate_ids", [])

        if len(candidate_ids) != 2:
            return {
                "status": "error",
                "message": "Exactly two candidates must be selected",
            }

        db = SessionLocal()
        try:
            # Delete existing TCP candidates for this division
            db.query(TCPCandidate).filter_by(electorate=division).delete()

            # Get candidate details
            candidates = (
                db.query(Candidate).filter(Candidate.id.in_(candidate_ids)).all()
            )

            # Create new TCP candidates
            for candidate in candidates:
                tcp_candidate = TCPCandidate(
                    electorate=division,
                    candidate_name=candidate.candidate_name,
                    party=candidate.party,
                )
                db.add(tcp_candidate)

            db.commit()
            return {
                "status": "success",
                "message": "TCP candidates updated successfully",
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error setting TCP candidates for {division}: {e}")
        return {"status": "error", "message": str(e)}


class CandidateResponse(BaseModel):
    id: int
    candidate_name: str
    party: Optional[str] = None
    electorate: str
    ballot_position: Optional[int] = None
    candidate_type: str
    state: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@app.get("/candidates")
async def get_candidates(
    division: Optional[str] = None,
    electorate: Optional[str] = None,
    candidate_type: Optional[str] = None,
):
    """
    Get candidates, optionally filtered by division/electorate and/or candidate type.
    Accepts either 'division' or 'electorate' parameter for backward compatibility.
    """
    try:
        db = SessionLocal()
        try:
            query = db.query(Candidate)

            # Use either division or electorate parameter
            division_name = division or electorate
            if division_name:
                query = query.filter(Candidate.electorate == division_name)
            if candidate_type:
                query = query.filter(Candidate.candidate_type == candidate_type)

            candidates = query.order_by(Candidate.ballot_position).all()

            return {
                "status": "success",
                "candidates": [
                    {
                        "id": c.id,
                        "candidate_name": c.candidate_name,
                        "party": c.party,
                        "electorate": c.electorate,
                        "ballot_position": c.ballot_position,
                        "candidate_type": c.candidate_type,
                        "state": c.state,
                        "data": json.loads(c.data) if c.data else {},
                    }
                    for c in candidates
                ],
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting candidates: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/polling-places/division/{division}")
async def get_polling_places(division: str):
    """
    Get polling places for a specific division
    """
    try:
        db = SessionLocal()
        try:
            # Get polling places directly from the database using SQLAlchemy
            polling_places = (
                db.query(PollingPlace)
                .filter(PollingPlace.division_name == division)
                .order_by(PollingPlace.polling_place_name)
                .all()
            )

            return {
                "status": "success",
                "polling_places": [
                    {
                        "id": p.id,
                        "polling_place_id": p.polling_place_id,
                        "polling_place_name": p.polling_place_name,
                        "address": p.address,
                        "status": p.status,
                        "wheelchair_access": p.wheelchair_access,
                        "data": json.loads(p.data) if p.data else {},
                    }
                    for p in polling_places
                ],
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting polling places for division {division}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/manual-entry")
async def manual_entry(request: Request):
    """
    Handle manual entry of booth results
    """
    try:
        data = await request.json()

        # Validate required fields
        if not data.get("booth_name") or not data.get("electorate"):
            raise HTTPException(
                status_code=400, detail="Booth name and electorate are required"
            )

        db = SessionLocal()
        try:
            # If updating existing result
            if data.get("result_id"):
                result = db.query(Result).filter_by(id=data["result_id"]).first()
                if not result:
                    raise HTTPException(status_code=404, detail="Result not found")

                result.booth_name = data["booth_name"]
                result.electorate = data["electorate"]
                result.data = json.dumps(
                    {
                        "primary_votes": data.get("primary_votes", {}),
                        "two_candidate_preferred": data.get(
                            "two_candidate_preferred", {}
                        ),
                        "totals": data.get("totals", {}),
                        "reviewed": True,
                        "approved": True,
                        "reviewed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                result.is_reviewed = 1
                result.reviewer = "Manual Entry"
                db_result = result
            else:
                # Create new result
                db_result = Result(
                    booth_name=data["booth_name"],
                    electorate=data["electorate"],
                    data=json.dumps(
                        {
                            "primary_votes": data.get("primary_votes", {}),
                            "two_candidate_preferred": data.get(
                                "two_candidate_preferred", {}
                            ),
                            "totals": data.get("totals", {}),
                            "reviewed": True,
                            "approved": True,
                            "reviewed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                    is_reviewed=1,
                    reviewer="Manual Entry",
                )
                db.add(db_result)

            db.commit()
            db.refresh(db_result)

            # Notify Flask app
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        FLASK_APP_URL,
                        json={
                            "result_id": db_result.id,
                            "timestamp": db_result.timestamp.isoformat(),
                            "electorate": db_result.electorate,
                            "booth_name": db_result.booth_name,
                            "action": "manual_entry",
                        },
                    )
            except Exception as notify_err:
                logger.error(f"Failed to notify Flask app: {notify_err}")

            return {
                "status": "success",
                "result_id": db_result.id,
                "message": "Result saved successfully",
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing manual entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/results/{result_id}/update-booth-name")
async def update_result_booth_name(result_id: int, request: Request):
    """
    Update the booth name for a specific result
    """
    try:
        data = await request.json()
        booth_name = data.get("booth_name")

        if not booth_name:
            raise HTTPException(status_code=400, detail="Booth name is required")

        db = SessionLocal()
        try:
            result = db.query(Result).filter_by(id=result_id).first()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Result with ID {result_id} not found"
                )

            result.booth_name = booth_name
            db.commit()

            return {
                "status": "success",
                "message": "Booth name updated successfully",
                "result": {
                    "id": result.id,
                    "booth_name": result.booth_name,
                },
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating booth name for result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
