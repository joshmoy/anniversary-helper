"""
Main FastAPI application for the Church Anniversary & Birthday Helper.
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, status, Depends, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.database import db_manager
from app.models import (
    Person, PersonUpdate, LoginRequest, LoginResponse, RegisterRequest, RegisterResponse, UserBase, UserCreate, UserRole,
    AnniversaryWishRequest, AnniversaryWishResponse, RegenerateWishRequest, CoordinatorDeliveryTestRequest, UserProfileUpdate,
    AnniversaryType, ToneType
)
from app.services import csv_manager, date_manager, coordinator_notifier, storage_manager
from app.scheduler import celebration_scheduler
from app.auth import auth_service, get_current_user, get_optional_current_user
from app.rate_limiter import rate_limit_service
from app.ai_wish_generator import ai_wish_generator

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def build_user_response(user) -> UserBase:
    """Build the standard user response payload."""
    return UserBase(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        phone_number=getattr(user, "phone_number", None),
        account_type=user.account_type,
        role=user.role,
        notification_preference=user.notification_preference,
        notification_channels=user.notification_channels,
        direct_message_channel=user.direct_message_channel,
        is_active=user.is_active,
    )


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
    description="""
    Automated system for sending Christian celebration messages and generating personalized anniversary wishes.
    
    ## Features
    
    * **Automated Celebrations**: Daily automated checks for birthdays and anniversaries
    * **CSV Data Management**: Easy monthly data uploads via CSV files
    * **AI-Generated Messages**: Creates personalized Christian messages with Bible verses
    * **Coordinator Delivery**: Sends the generated daily message to one coordinator over SMS, email, WhatsApp, or Telegram
    * **Anniversary Wish API**: Generate personalized AI-powered anniversary wishes
    * **Rate Limiting**: Protects API endpoints with configurable rate limits
    
    ## Anniversary Wish API
    
    The Anniversary Wish API allows users to generate personalized, AI-powered anniversary wishes:
    
    * **Public Access**: Non-authenticated users can generate wishes (with rate limiting)
    * **Rate Limiting**: 3 requests per 3 hours per IP address for non-authenticated users
    * **AI-Powered**: Uses Groq/OpenAI to generate contextually appropriate wishes
    * **Christian-Themed**: All wishes include appropriate Bible verses
    * **Personalized**: Considers relationship type, anniversary type, and custom context
    
    ## Authentication
    
    * Management endpoints require a valid JWT (any authenticated user)
    * Anniversary wish endpoints work without authentication (with rate limiting)
    * Authenticated users have unlimited access to wish generation
    """,
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "Church Anniversary Helper Support",
        "email": "support@anniversaryhelper.com",
    },
    license_info={
        "name": "MIT",
    },
)

allowed_origins = [
    settings.job_url,
    settings.frontend_url,
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in allowed_origins if origin], 
    allow_origin_regex=r"^https://(www\.)?anniversaryhelper\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Health check endpoint.

    Verifies the database connection with a light metadata probe that is not
    tenant-scoped, so the endpoint stays usable without authentication.
    """
    try:
        if db_manager.supabase is None:
            raise Exception("Database not initialized")
        # Cheap ping that doesn't return tenant data.
        db_manager.supabase.table("users").select("id").limit(1).execute()

        scheduler_status = celebration_scheduler.get_status()

        return {
            "status": "healthy",
            "database": "connected",
            "scheduler": scheduler_status,
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
    User login endpoint.
    
    Creates a session token for authenticated users.
    """
    try:
        user = await db_manager.get_user_by_email(login_data.email)
        
        if not user:
            logger.warning(f"Login attempt with invalid email: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        if not user.is_active:
            logger.warning(f"Login attempt with inactive user: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )
        
        if not auth_service.verify_password(login_data.password, user.password_hash):
            logger.warning(f"Login attempt with invalid password for user: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        await db_manager.update_user_last_login(user.id)
        
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "account_type": user.account_type.value if hasattr(user.account_type, "value") else user.account_type,
            "type": "access"
        }
        access_token = auth_service.create_access_token(token_data)
        
        logger.info(f"Successful login for user: {user.username}")
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=build_user_response(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@app.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(register_data: RegisterRequest):
    """
    Register a new user account.
    """
    try:
        existing_username = await db_manager.get_user_by_username(register_data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this username already exists"
            )

        existing_email = await db_manager.get_user_by_email(register_data.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists"
            )

        password_hash = auth_service.get_password_hash(register_data.password)
        user = await db_manager.create_user(
            user_data=UserCreate(
                username=register_data.username,
                email=register_data.email,
                full_name=register_data.full_name,
                phone_number=register_data.phone_number,
                account_type=register_data.account_type,
                role=UserRole.MEMBER,
                notification_preference=register_data.notification_preference,
                notification_channels=register_data.notification_channels,
                direct_message_channel=register_data.direct_message_channel,
                is_active=True,
                password=register_data.password,
            ),
            password_hash=password_hash
        )

        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "account_type": user.account_type.value if hasattr(user.account_type, "value") else user.account_type,
            "type": "access"
        }
        access_token = auth_service.create_access_token(token_data)

        logger.info(
            "Registered new account for %s with account type %s",
            register_data.email,
            register_data.account_type,
        )

        return RegisterResponse(
            message="Registration successful",
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=build_user_response(user)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration"
        )


@app.get("/auth/me", response_model=UserBase)
async def get_current_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    This endpoint can be used to verify authentication tokens.
    """
    try:
        user = await db_manager.get_user_by_id(current_user["id"])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return build_user_response(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.put("/auth/me", response_model=UserBase)
async def update_current_user_info(
    profile_data: UserProfileUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update the current user's profile and delivery preferences.
    """
    try:
        user = await db_manager.update_user_profile(current_user["id"], profile_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return build_user_response(user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating current user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/people", response_model=List[Person])
async def get_all_people(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get the caller's people."""
    try:
        return await db_manager.get_all_people(owner_user_id=current_user["id"])
    except Exception as e:
        logger.error(f"Error getting people: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/people/{person_id}", response_model=Person)
async def get_person(person_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get one of the caller's people by ID."""
    try:
        person = await db_manager.get_person_by_id(
            person_id, owner_user_id=current_user["id"]
        )
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        return person
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/people/{person_id}", response_model=Person)
async def update_person(person_id: int, person_data: PersonUpdate, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update one of the caller's people."""
    try:
        updated_person = await db_manager.update_person(
            person_id, person_data, owner_user_id=current_user["id"]
        )
        if not updated_person:
            raise HTTPException(status_code=404, detail="Person not found")
        return updated_person
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/people/{person_id}")
async def delete_person(person_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Soft-delete one of the caller's people."""
    try:
        success = await db_manager.delete_person(
            person_id, owner_user_id=current_user["id"]
        )
        if not success:
            raise HTTPException(status_code=404, detail="Person not found")
        return {"message": "Person deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/celebrations/today", response_model=List[Person])
async def get_todays_celebrations(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get today's celebrations for the caller."""
    try:
        return await date_manager.get_todays_celebrations(owner_user_id=current_user["id"])
    except Exception as e:
        logger.error(f"Error getting today's celebrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/celebrations/{date_str}", response_model=List[Person])
async def get_celebrations_for_date(date_str: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get celebrations for ``date_str`` (MM-DD) scoped to the caller."""
    try:
        if len(date_str) != 5 or date_str[2] != '-':
            raise HTTPException(status_code=400, detail="Date must be in MM-DD format")

        return await db_manager.get_people_by_date(
            date_str, owner_user_id=current_user["id"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting celebrations for {date_str}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-csv")
async def upload_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...), current_user: Dict[str, Any] = Depends(get_current_user)):
    """Upload a CSV; its rows land in the caller's people set."""
    try:
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")

        file_content = await file.read()

        upload_result = await storage_manager.upload_csv_file(
            file_content, file.filename, owner_user_id=current_user["id"]
        )

        if not upload_result["success"]:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to upload file to storage: {upload_result.get('error', 'Unknown error')}"
            )

        background_tasks.add_task(
            process_csv_background,
            upload_result["file_path"],
            current_user["id"],
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


async def process_csv_background(file_path: str, owner_user_id: int):
    """Background task to process an owner's CSV upload."""
    try:
        result = await csv_manager.process_csv_file(file_path, owner_user_id=owner_user_id)
        logger.info(f"CSV processing completed: {result}")
    except Exception as e:
        logger.error(f"Error processing CSV in background: {e}")
        

@app.post("/scheduler/cron-hook")
async def cron_hook(x_cron_secret: str | None = Header(None)):
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    await celebration_scheduler.run_manual_check()
    return {"message": "ok"}


@app.post("/send-celebrations")
async def send_daily_celebrations(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Manually trigger today's celebration delivery for the current user."""
    try:
        user = await db_manager.get_user_by_id(current_user["id"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        result = await coordinator_notifier.send_daily_celebrations_for_user(user)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending celebrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/test-coordinator-delivery")
async def test_coordinator_delivery(
    test_request: CoordinatorDeliveryTestRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send a test notification to the current user's configured channels."""
    try:
        user = await db_manager.get_user_by_id(current_user["id"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        subject = test_request.subject or "Coordinator delivery test"
        message = test_request.message or (
            "This is a test coordinator notification from the Church Anniversary & Birthday Helper.\n\n"
            "If you received this, your configured delivery channel is working."
        )

        result = await coordinator_notifier.send_test_message_to_user(user, message, subject=subject)
        return {
            "message": "Coordinator delivery test completed",
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending coordinator delivery test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/messages")
async def get_message_logs(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get the caller's message logs."""
    try:
        return await db_manager.get_all_message_logs(owner_user_id=current_user["id"])
    except Exception as e:
        logger.error(f"Error getting message logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/messages/{message_id}")
async def get_message_log(message_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get one of the caller's message logs by ID."""
    try:
        message = await db_manager.get_message_log_by_id(
            message_id, owner_user_id=current_user["id"]
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message log {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/csv-uploads")
async def get_csv_upload_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get the caller's CSV upload history."""
    try:
        return await db_manager.get_csv_upload_history(owner_user_id=current_user["id"])
    except Exception as e:
        logger.error(f"Error getting CSV upload history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/csv-files")
async def list_csv_files(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List the caller's CSV files in storage."""
    try:
        files = await storage_manager.list_csv_files(owner_user_id=current_user["id"])
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing CSV files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/csv-files/{file_path:path}")
async def delete_csv_file(file_path: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Delete one of the caller's CSV files from storage."""
    try:
        success = await storage_manager.delete_csv_file(
            file_path, owner_user_id=current_user["id"]
        )
        if not success:
            raise HTTPException(status_code=404, detail="File not found or could not be deleted")
        return {"message": "File deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting CSV file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scheduler/status")
async def get_scheduler_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get the current status of the celebration scheduler. Requires authentication."""
    try:
        return celebration_scheduler.get_status()
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scheduler/manual-run")
async def manual_scheduler_run(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Manually trigger the celebration scheduler (for testing). Requires authentication."""
    try:
        await celebration_scheduler.run_manual_check()
        return {"message": "Manual celebration check completed"}
    except Exception as e:
        logger.error(f"Error in manual scheduler run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Anniversary Wish API Endpoints
@app.post("/api/anniversary-wish", response_model=AnniversaryWishResponse)
async def generate_anniversary_wish(
    request: AnniversaryWishRequest,
    http_request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """
    Generate a personalized AI-powered anniversary wish.
    
    This endpoint allows both authenticated and non-authenticated users to generate
    anniversary wishes. Non-authenticated users are subject to rate limiting.
    
    ## Rate Limiting
    - **Non-authenticated users**: 3 requests per 3 hours per IP address
    - **Authenticated users**: Unlimited requests
    
    ## Example Request
    ```json
    {
        "name": "John and Sarah",
        "anniversary_type": "wedding-anniversary",
        "relationship": "friend",
        "tone": "warm",
        "context": "They just moved to a new city and are starting a new chapter"
    }
    ```
    
    ## Relationship Examples
    You can use any relationship description, such as:
    - "friend", "best friend", "close friend"
    - "colleague", "coworker", "boss", "manager"
    - "spouse", "husband", "wife", "partner"
    - "parent", "mother", "father"
    - "child", "son", "daughter"
    - "sibling", "brother", "sister"
    - "mentor", "teacher", "pastor", "minister"
    - "neighbor", "family member", "relative"
    - Or any custom relationship description
    
    ## Example Response
    ```json
    {
        "generated_wish": "🎉 Happy 5th Wedding Anniversary, John and Sarah! As your friend, I'm so grateful to celebrate this beautiful milestone with you. May God continue to bless your marriage as you begin this new chapter in your new city. - Love is patient, love is kind. It does not envy, it does not boast, it is not proud. (1 Corinthians 13:4)",
        "request_id": "123e4567-e89b-12d3-a456-426614174000",
        "remaining_requests": 2,
        "window_reset_time": "2024-01-15T18:00:00Z"
    }
    ```
    """
    try:
        # Extract IP address for rate limiting
        ip_address = rate_limit_service.extract_ip_address(http_request)
        
        # Check rate limits for non-authenticated users
        if not current_user:
            is_allowed, rate_info = await rate_limit_service.check_rate_limit(ip_address)
            
            if not is_allowed:
                retry_after = rate_info.get("retry_after_seconds", 3600)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(retry_after)}
                )
        else:
            # Authenticated users have unlimited access
            rate_info = {
                "remaining_requests": 999,
                "window_reset_time": None,
                "request_count": 0
            }

        # Generate a unique request ID
        request_id = str(uuid.uuid4())

        owner_user_id = current_user["id"] if current_user else None

        # Generate the anniversary wish with audit logging
        generated_wish = await ai_wish_generator.generate_anniversary_wish(
            request, request_id, ip_address, owner_user_id=owner_user_id
        )
        
        # Prepare response
        response = AnniversaryWishResponse(
            generated_wish=generated_wish,
            request_id=request_id,
            remaining_requests=rate_info.get("remaining_requests", 0),
            window_reset_time=rate_info.get("window_reset_time")
        )
        
        logger.info(f"Generated anniversary wish for {request.name} (IP: {ip_address}, Request ID: {request_id})")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating anniversary wish: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate anniversary wish. Please try again later."
        )


@app.post("/api/anniversary-wish/regenerate", response_model=AnniversaryWishResponse)
async def regenerate_anniversary_wish(
    request: RegenerateWishRequest,
    http_request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """
    Regenerate an anniversary wish with additional context.
    
    This endpoint allows users to regenerate wishes they're not satisfied with,
    optionally providing additional context for refinement.
    """
    try:
        # Extract IP address for rate limiting
        ip_address = rate_limit_service.extract_ip_address(http_request)
        
        # Check rate limits for non-authenticated users
        if not current_user:
            is_allowed, rate_info = await rate_limit_service.check_rate_limit(ip_address)
            
            if not is_allowed:
                retry_after = rate_info.get("retry_after_seconds", 3600)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(retry_after)}
                )
        else:
            # Authenticated users have unlimited access
            rate_info = {
                "remaining_requests": 999,
                "window_reset_time": None,
                "request_count": 0
            }

        owner_user_id = current_user["id"] if current_user else None

        # Look up the original request. Authenticated callers are scoped to
        # their own request history; anonymous callers can still regenerate by
        # id (the generated wish is not returned unless the original exists).
        original_audit_log = await db_manager.get_ai_wish_audit_log_by_request_id(
            request.request_id, owner_user_id=owner_user_id
        )
        
        if not original_audit_log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original request not found. Cannot regenerate."
            )
        
        # Reconstruct the original request
        original_request_data = original_audit_log.request_data
        original_request = AnniversaryWishRequest(**original_request_data)
        
        new_request_id = str(uuid.uuid4())

        generated_wish = await ai_wish_generator.regenerate_wish(
            original_request,
            request.request_id,
            new_request_id,
            ip_address,
            request.additional_context,
            owner_user_id=owner_user_id,
        )
        
        # Prepare response
        response = AnniversaryWishResponse(
            generated_wish=generated_wish,
            request_id=new_request_id,
            remaining_requests=rate_info.get("remaining_requests", 0),
            window_reset_time=rate_info.get("window_reset_time")
        )
        
        logger.info(f"Regenerated anniversary wish for {original_request.name} (Original Request ID: {request.request_id}, New Request ID: {new_request_id})")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating anniversary wish: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate anniversary wish. Please try again later."
        )


@app.get("/api/anniversary-wish/rate-limit-info")
async def get_rate_limit_info(
    http_request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user)
):
    """
    Get current rate limit information for the requesting IP address.
    
    This endpoint is useful for clients to check their current rate limit status
    before making requests. It does not count against the rate limit.
    
    ## Example Response
    ```json
    {
        "ip_address": "192.168.1.100",
        "is_authenticated": false,
        "rate_limit_info": {
            "remaining_requests": 2,
            "window_reset_time": "2024-01-15T18:00:00Z",
            "request_count": 1
        }
    }
    ```
    """
    try:
        # Extract IP address
        ip_address = rate_limit_service.extract_ip_address(http_request)
        
        # Get rate limit information
        rate_info = await rate_limit_service.get_rate_limit_info(ip_address)
        
        return {
            "ip_address": ip_address,
            "is_authenticated": current_user is not None,
            "rate_limit_info": rate_info
        }
        
    except Exception as e:
        logger.error(f"Error getting rate limit info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rate limit information."
        )


@app.get("/admin/ai-wish-audit-logs")
async def get_ai_wish_audit_logs(
    limit: int = 100,
    offset: int = 0,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get AI wish generation audit logs.

    Returns the audit trail of all AI wish generation requests.
    """
    try:
        audit_logs = await db_manager.get_ai_wish_audit_logs(
            limit=limit, offset=offset, owner_user_id=current_user["id"]
        )
        return {
            "audit_logs": audit_logs,
            "total_returned": len(audit_logs),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error getting AI wish audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit logs."
        )


@app.get("/admin/ai-wish-audit-logs/{request_id}")
async def get_ai_wish_audit_log_by_id(
    request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a specific AI wish audit log by request ID.
    """
    try:
        audit_log = await db_manager.get_ai_wish_audit_log_by_request_id(
            request_id, owner_user_id=current_user["id"]
        )
        if not audit_log:
            raise HTTPException(status_code=404, detail="Audit log not found")
        return audit_log
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI wish audit log {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit log."
        )


@app.get("/admin/ai-wish-regeneration-chain/{original_request_id}")
async def get_ai_wish_regeneration_chain(
    original_request_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all regenerations for a given original request ID.
    """
    try:
        regeneration_chain = await db_manager.get_ai_wish_regeneration_chain(
            original_request_id, owner_user_id=current_user["id"]
        )
        return {
            "original_request_id": original_request_id,
            "regenerations": regeneration_chain,
            "total_regenerations": len(regeneration_chain)
        }
    except Exception as e:
        logger.error(f"Error getting regeneration chain for {original_request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get regeneration chain."
        )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development"
    )
