import os
import re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from PIL import Image
import pytesseract
import io
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import logging
from typing import Dict, List, Optional, Any, Tuple

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

SQLALCHEMY_DATABASE_URL = "sqlite:///./results.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    electorate = Column(String, index=True)
    booth_name = Column(String, index=True)
    data = Column(JSON)

Base.metadata.create_all(bind=engine)
def extract_tally_sheet_data(extracted_rows: List[List[str]]) -> Dict[str, Any]:
    """
    Extract structured data from tally sheet rows
    """
    result = {
        "electorate": None,
        "booth_name": None,
        "primary_votes": {},
        "two_candidate_preferred": {},
        "totals": {
            "formal": None,
            "informal": None,
            "total": None
        }
    }
    
    for row in extracted_rows[:5]:  # Check first few rows
        row_text = " ".join(row).strip()
        if "TALLY SHEET" in row_text:
            match = re.search(r"([A-Z\s']+)'?S SCRUTINEER TALLY SHEET", row_text)
            if match:
                result["electorate"] = match.group(1).strip()
            break
    
    for i, row in enumerate(extracted_rows[:10]):  # Check first few rows
        row_text = " ".join(row).strip()
        if "BOOTH NAME" in row_text or "BOOTH NAME:" in row_text:
            booth_parts = row_text.split(":")
            if len(booth_parts) > 1 and booth_parts[1].strip():
                result["booth_name"] = booth_parts[1].strip()
            elif i+1 < len(extracted_rows):
                next_row = " ".join(extracted_rows[i+1]).strip()
                if not any(keyword in next_row for keyword in ["YOUR NAME", "MOBILE", "Please record"]):
                    result["booth_name"] = next_row
            break
    
    table_start_idx = None
    table_end_idx = None
    
    for i, row in enumerate(extracted_rows):
        row_text = " ".join(row).strip().upper()
        if "CANDIDATE" in row_text and "PRIMARY" in row_text and "VOTES" in row_text:
            table_start_idx = i
        if table_start_idx and "TOTAL VOTES" in row_text:
            table_end_idx = i
            break
    
    if table_start_idx and table_end_idx:
        tcp_headers = []
        for i in range(table_start_idx+1, table_start_idx+3):
            if i < len(extracted_rows):
                row = extracted_rows[i]
                if any("STEGGALL" in word for word in row) or any("ROGERS" in word for word in row):
                    tcp_headers = row
                    break
        
        for i in range(table_start_idx+1, table_end_idx):
            if i >= len(extracted_rows):
                break
                
            row = extracted_rows[i]
            if not row or len(row) < 2:
                continue
                
            if any(header in " ".join(row).upper() for header in ["CANDIDATE", "STEGGALL", "ROGERS"]):
                continue
                
            candidate_info = row[0] if len(row) > 0 else ""
            
            if not candidate_info or "Total" in candidate_info:
                if "Total Formal Votes" in " ".join(row):
                    if len(row) > 1 and row[1].strip() and row[1].strip().isdigit():
                        result["totals"]["formal"] = int(row[1].strip())
                elif "Informal" in " ".join(row):
                    if len(row) > 1 and row[1].strip() and row[1].strip().isdigit():
                        result["totals"]["informal"] = int(row[1].strip())
                elif "Total Votes" in " ".join(row):
                    if len(row) > 1 and row[1].strip() and row[1].strip().isdigit():
                        result["totals"]["total"] = int(row[1].strip())
                continue
                
            primary_votes = None
            if len(row) > 1 and row[1].strip():
                try:
                    primary_votes = int(row[1].strip())
                    result["primary_votes"][candidate_info] = primary_votes
                except ValueError:
                    pass
            
            if len(tcp_headers) >= 2 and len(row) > 2:
                for j in range(2, min(len(row), len(tcp_headers))):
                    if tcp_headers[j].strip() and row[j].strip():
                        try:
                            tcp_votes = int(row[j].strip())
                            tcp_candidate = tcp_headers[j].strip()
                            if tcp_candidate not in result["two_candidate_preferred"]:
                                result["two_candidate_preferred"][tcp_candidate] = {}
                            result["two_candidate_preferred"][tcp_candidate][candidate_info] = tcp_votes
                        except ValueError:
                            pass
    
    return result


FLASK_APP_URL = os.environ.get("FLASK_APP_URL", "http://localhost:5000/api/notify")

@app.post("/scan-image")
async def scan_image(file: UploadFile = File(...)):
    """
    Scan an uploaded image file and extract tally sheet data
    """
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("L")  # Convert to grayscale
        
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        extracted_rows = []
        current_row = []
        last_top = None
        
        for i, word in enumerate(data['text']):
            if word.strip() == "":
                continue
            top = data['top'][i]
            if last_top is None or abs(top - last_top) < 15:
                current_row.append(word)
            else:
                if current_row:
                    extracted_rows.append(current_row)
                current_row = [word]
            last_top = top
        
        if current_row:
            extracted_rows.append(current_row)
        
        # Extract structured data from the tally sheet
        tally_data = extract_tally_sheet_data(extracted_rows)
        
        db = SessionLocal()
        try:
            image_url = f"temp/{file.filename}"
            
            db_result = Result(
                image_url=image_url,
                electorate=tally_data.get("electorate"),
                booth_name=tally_data.get("booth_name"),
                data={
                    "raw_rows": extracted_rows,
                    "primary_votes": tally_data.get("primary_votes"),
                    "two_candidate_preferred": tally_data.get("two_candidate_preferred"),
                    "totals": tally_data.get("totals")
                }
            )
            db.add(db_result)
            db.commit()
            db.refresh(db_result)
            
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        FLASK_APP_URL,
                        json={
                            "result_id": db_result.id, 
                            "timestamp": db_result.timestamp.isoformat(),
                            "electorate": tally_data.get("electorate"),
                            "booth_name": tally_data.get("booth_name")
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to notify Flask app: {e}")
            
            return {
                "status": "success",
                "result_id": db_result.id,
                "electorate": tally_data.get("electorate"),
                "booth_name": tally_data.get("booth_name"),
                "primary_votes": tally_data.get("primary_votes"),
                "two_candidate_preferred": tally_data.get("two_candidate_preferred"),
                "totals": tally_data.get("totals")
            }
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/inbound-sms")
async def receive_sms(request: Request):
    """
    Process SMS with attached media for tally sheet scanning
    """
    payload = await request.json()
    
    text = payload.get("body")
    media_urls = payload.get("media", [])
    
    extracted_rows = []
    
    for media_url in media_urls:
        async with httpx.AsyncClient() as client:
            response = await client.get(media_url)
            image_data = response.content
        
        image = Image.open(io.BytesIO(image_data)).convert("L")  # Convert to grayscale
        
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        current_row = []
        last_top = None
        
        for i, word in enumerate(data['text']):
            if word.strip() == "":
                continue
            top = data['top'][i]
            if last_top is None or abs(top - last_top) < 15:
                current_row.append(word)
            else:
                if current_row:
                    extracted_rows.append(current_row)
                current_row = [word]
            last_top = top
        
        if current_row:
            extracted_rows.append(current_row)
    
    # Extract structured data from the tally sheet
    tally_data = extract_tally_sheet_data(extracted_rows)
    
    db = SessionLocal()
    try:
        image_url = media_urls[0] if media_urls else None
        
        db_result = Result(
            image_url=image_url,
            electorate=tally_data.get("electorate"),
            booth_name=tally_data.get("booth_name"),
            data={
                "raw_rows": extracted_rows,
                "primary_votes": tally_data.get("primary_votes"),
                "two_candidate_preferred": tally_data.get("two_candidate_preferred"),
                "totals": tally_data.get("totals"),
                "text": text
            }
        )
        db.add(db_result)
        db.commit()
        db.refresh(db_result)
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    FLASK_APP_URL,
                    json={
                        "result_id": db_result.id, 
                        "timestamp": db_result.timestamp.isoformat(),
                        "electorate": tally_data.get("electorate"),
                        "booth_name": tally_data.get("booth_name")
                    }
                )
        except Exception as e:
            logger.error(f"Failed to notify Flask app: {e}")
        
        return {
            "status": "received", 
            "result_id": db_result.id,
            "electorate": tally_data.get("electorate"),
            "booth_name": tally_data.get("booth_name"),
            "primary_votes": tally_data.get("primary_votes"),
            "two_candidate_preferred": tally_data.get("two_candidate_preferred"),
            "totals": tally_data.get("totals")
        }
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
