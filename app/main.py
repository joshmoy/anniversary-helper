"""
Main FastAPI application for the Church Anniversary & Birthday Helper.
"""
import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.database import db_manager
from app.models import Person, PersonUpdate, LoginRequest, LoginResponse, AdminBase
from app.services import csv_manager, date_manager, whatsapp_messenger, storage_manager
from app.scheduler import celebration_scheduler
from app.auth import auth_service, get_current_admin

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
        "http://127.0.0.1:3002",
        "http://localhost:3002",  # Alternative port
        
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


@app.post("/auth/login", response_model=LoginResponse)
async def login(login_data: LoginRequest):
    """
    Admin login endpoint.
    
    Creates a session token for authenticated admin users.
    """
    try:
        # Get admin by username
        admin = await db_manager.get_admin_by_username(login_data.username)
        
        if not admin:
            logger.warning(f"Login attempt with invalid username: {login_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Check if admin is active
        if not admin.is_active:
            logger.warning(f"Login attempt with inactive admin: {login_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )
        
        # Verify password
        if not auth_service.verify_password(login_data.password, admin.password_hash):
            logger.warning(f"Login attempt with invalid password for user: {login_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Update last login timestamp
        await db_manager.update_admin_last_login(admin.id)
        
        # Create access token
        token_data = {
            "sub": str(admin.id),  # JWT sub must be a string
            "username": admin.username,
            "type": "access"
        }
        access_token = auth_service.create_access_token(token_data)
        
        logger.info(f"Successful login for admin: {admin.username}")
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,  # Convert to seconds
            admin=AdminBase(username=admin.username, is_active=admin.is_active)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@app.get("/auth/me", response_model=AdminBase)
async def get_current_admin_info(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Get current authenticated admin information.
    
    This endpoint can be used to verify authentication tokens.
    """
    try:
        admin = await db_manager.get_admin_by_id(current_admin["id"])
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin not found"
            )
        
        return AdminBase(username=admin.username, is_active=admin.is_active)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current admin info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/people", response_model=List[Person])
async def get_all_people(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get all people in the database. Requires authentication."""
    try:
        return await db_manager.get_all_people()
    except Exception as e:
        logger.error(f"Error getting people: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/people/{person_id}", response_model=Person)
async def get_person(person_id: int, current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get a specific person by ID. Requires authentication."""
    try:
        person = await db_manager.get_person_by_id(person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        return person
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/people/{person_id}", response_model=Person)
async def update_person(person_id: int, person_data: PersonUpdate, current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Update a person's information. Requires authentication."""
    try:
        updated_person = await db_manager.update_person(person_id, person_data)
        if not updated_person:
            raise HTTPException(status_code=404, detail="Person not found")
        return updated_person
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/people/{person_id}")
async def delete_person(person_id: int, current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Delete a person (soft delete by setting active=False). Requires authentication."""
    try:
        success = await db_manager.delete_person(person_id)
        if not success:
            raise HTTPException(status_code=404, detail="Person not found")
        return {"message": "Person deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/celebrations/today", response_model=List[Person])
async def get_todays_celebrations(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get all people with celebrations today. Requires authentication."""
    try:
        return await date_manager.get_todays_celebrations()
    except Exception as e:
        logger.error(f"Error getting today's celebrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/celebrations/{date_str}", response_model=List[Person])
async def get_celebrations_for_date(date_str: str, current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get all people with celebrations on a specific date (MM-DD format). Requires authentication."""
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
async def upload_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...), current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Upload and process a CSV file with celebration data using Supabase Storage. Requires authentication."""
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")

        # Read file content
        file_content = await file.read()

        # Upload to Supabase Storage
        upload_result = await storage_manager.upload_csv_file(file_content, file.filename)
        
        if not upload_result["success"]:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to upload file to storage: {upload_result.get('error', 'Unknown error')}"
            )

        # Process CSV in background
        background_tasks.add_task(
            process_csv_background, 
            upload_result["file_path"]
        )

        return {
            "message": "CSV file uploaded successfully to cloud storage",
            "filename": file.filename,
            "status": "processing"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_csv_background(file_path: str):
    """Background task to process CSV file from Supabase Storage."""
    try:
        result = await csv_manager.process_csv_file(file_path)
        logger.info(f"CSV processing completed: {result}")
    except Exception as e:
        logger.error(f"Error processing CSV in background: {e}")


@app.post("/send-celebrations")
async def send_daily_celebrations(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Manually trigger sending celebration messages for today. Requires authentication."""
    try:
        result = await whatsapp_messenger.send_daily_celebrations()
        return result
    except Exception as e:
        logger.error(f"Error sending celebrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/messages")
async def get_message_logs(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get all message logs with delivery status. Requires authentication."""
    try:
        messages = await db_manager.get_all_message_logs()
        return messages
    except Exception as e:
        logger.error(f"Error getting message logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/messages/{message_id}")
async def get_message_log(message_id: int, current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get a specific message log by ID. Requires authentication."""
    try:
        message = await db_manager.get_message_log_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message log {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/csv-uploads")
async def get_csv_upload_history(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get the history of all CSV uploads. Requires authentication."""
    try:
        uploads = await db_manager.get_csv_upload_history()
        return uploads
    except Exception as e:
        logger.error(f"Error getting CSV upload history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/csv-files")
async def list_csv_files(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """List all CSV files in Supabase Storage. Requires authentication."""
    try:
        files = await storage_manager.list_csv_files()
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing CSV files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/csv-files/{file_path:path}")
async def delete_csv_file(file_path: str, current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Delete a CSV file from Supabase Storage. Requires authentication."""
    try:
        success = await storage_manager.delete_csv_file(file_path)
        if not success:
            raise HTTPException(status_code=404, detail="File not found or could not be deleted")
        return {"message": "File deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting CSV file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scheduler/status")
async def get_scheduler_status(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Get the current status of the celebration scheduler. Requires authentication."""
    try:
        return celebration_scheduler.get_status()
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scheduler/manual-run")
async def manual_scheduler_run(current_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Manually trigger the celebration scheduler (for testing). Requires authentication."""
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
