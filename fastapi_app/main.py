import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from PIL import Image
import pytesseract
import io
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import logging

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
    data = Column(JSON)

Base.metadata.create_all(bind=engine)

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
        
        db = SessionLocal()
        try:
            image_url = f"temp/{file.filename}"
            
            db_result = Result(
                image_url=image_url,
                data={"rows": extracted_rows}
            )
            db.add(db_result)
            db.commit()
            db.refresh(db_result)
            
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        FLASK_APP_URL,
                        json={"result_id": db_result.id, "timestamp": db_result.timestamp.isoformat()}
                    )
            except Exception as e:
                logger.error(f"Failed to notify Flask app: {e}")
            
            return {
                "status": "success",
                "result_id": db_result.id,
                "rows": extracted_rows
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
    
    db = SessionLocal()
    try:
        image_url = media_urls[0] if media_urls else None
        
        db_result = Result(
            image_url=image_url,
            data={"rows": extracted_rows, "text": text}
        )
        db.add(db_result)
        db.commit()
        db.refresh(db_result)
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    FLASK_APP_URL,
                    json={"result_id": db_result.id, "timestamp": db_result.timestamp.isoformat()}
                )
        except Exception as e:
            logger.error(f"Failed to notify Flask app: {e}")
        
        return {"status": "received", "rows": extracted_rows, "result_id": db_result.id}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
