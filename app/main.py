"""
Main FastAPI application for the Church Anniversary & Birthday Helper.
"""
import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.database import db_manager
from app.models import Person
from app.services import csv_manager, date_manager, whatsapp_messenger
from app.scheduler import celebration_scheduler

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Church Anniversary & Birthday Helper...")

    try:
        # Initialize database
        await db_manager.initialize_tables()

        # Start scheduler
        celebration_scheduler.start()

        logger.info("Application started successfully")

    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application...")
    celebration_scheduler.stop()


# Create FastAPI app
app = FastAPI(
    title="Church Anniversary & Birthday Helper",
    description="Automated system for sending Christian celebration messages",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js frontend
        "http://127.0.0.1:3000",
        "http://localhost:3001",  # Alternative port
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)


@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "message": "Church Anniversary & Birthday Helper API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        people = await db_manager.get_all_people()

        # Check scheduler status
        scheduler_status = celebration_scheduler.get_status()

        return {
            "status": "healthy",
            "database": "connected",
            "scheduler": scheduler_status,
            "total_people": len(people)
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.get("/people", response_model=List[Person])
async def get_all_people():
    """Get all people in the database."""
    try:
        return await db_manager.get_all_people()
    except Exception as e:
        logger.error(f"Error getting people: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/celebrations/today", response_model=List[Person])
async def get_todays_celebrations():
    """Get all people with celebrations today."""
    try:
        return await date_manager.get_todays_celebrations()
    except Exception as e:
        logger.error(f"Error getting today's celebrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/celebrations/{date_str}", response_model=List[Person])
async def get_celebrations_for_date(date_str: str):
    """Get all people with celebrations on a specific date (MM-DD format)."""
    try:
        # Validate date format
        if len(date_str) != 5 or date_str[2] != '-':
            raise HTTPException(status_code=400, detail="Date must be in MM-DD format")

        return await db_manager.get_people_by_date(date_str)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting celebrations for {date_str}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-csv")
async def upload_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload and process a CSV file with celebration data."""
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")

        # Save uploaded file
        upload_path = Path(settings.csv_upload_path)
        upload_path.mkdir(exist_ok=True)

        file_path = upload_path / f"{date.today().isoformat()}_{file.filename}"

        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Process CSV in background
        background_tasks.add_task(process_csv_background, str(file_path))

        return {
            "message": "CSV file uploaded successfully",
            "filename": file.filename,
            "status": "processing"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_csv_background(file_path: str):
    """Background task to process CSV file."""
    try:
        result = await csv_manager.process_csv_file(file_path)
        logger.info(f"CSV processing completed: {result}")
    except Exception as e:
        logger.error(f"Error processing CSV in background: {e}")


@app.post("/send-celebrations")
async def send_daily_celebrations():
    """Manually trigger sending celebration messages for today."""
    try:
        result = await whatsapp_messenger.send_daily_celebrations()
        return result
    except Exception as e:
        logger.error(f"Error sending celebrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scheduler/status")
async def get_scheduler_status():
    """Get the current status of the celebration scheduler."""
    try:
        return celebration_scheduler.get_status()
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scheduler/manual-run")
async def manual_scheduler_run():
    """Manually trigger the celebration scheduler (for testing)."""
    try:
        await celebration_scheduler.run_manual_check()
        return {"message": "Manual celebration check completed"}
    except Exception as e:
        logger.error(f"Error in manual scheduler run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development"
    )
