"""
API routes for webhook handlers.
"""
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Depends
from typing import Dict, Any, Optional
import structlog
import os

from ...db.repositories.factory import get_clips_repository
from ...services.factory import get_video_service
from ...services.video_service import VideoService
from ...api.models.core import AnalysisStatus

BASE_URL = "http://localhost:8000"

# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from svix.webhooks import Webhook, WebhookVerificationError
from .routers import raven
from .database import init_db, close_db, get_db_pool
from .pymodels import *
import os
from dotenv import load_dotenv
import asyncpg
import uvicorn

load_dotenv()

app = FastAPI()

# Get the Clerk webhook secret from environment variables
webhook_secret = os.getenv("CLERK_WEBHOOK_SECRET")
if not webhook_secret:
    raise ValueError("CLERK_WEBHOOK_SECRET environment variable not set!")

# --- CORS ---
origins = [
    "https://useraven.app",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- CORS ---

@app.post("/clerk-webhook")
async def clerk_webhook(request: Request, db: asyncpg.Connection = Depends(get_db_pool)):
    """Handles Clerk webhooks."""
    print("request: ", request)
    payload = await request.body()
    print("payload: ", payload)
    headers = request.headers
    print("header: ", headers)
    try:
        wh = Webhook(webhook_secret)
        print("wb: ", wh)
        evt = wh.verify(payload, headers)  # Verify the webhook signature
        print("evt: ", evt)
        data = evt['data']
        print("data: ", data)
        event_type = evt['type']
        print("evt_type: ", event_type)
        event_id = headers.get('svix-id') # Get the event ID for idempotency
        print("event_id: ", event_id)


    except WebhookVerificationError as e:
        print("WebhookVerificationError", e)
        raise HTTPException(status_code=400, detail=f"Webhook verification failed: {e}")
    except Exception as e:
        print("Exception: ", e)
        raise HTTPException(status_code=400, detail=str(e))

    # Check if we've already processed this event (idempotency)
    try:
        try:
            print(f"Checking for existing event with ID: {event_id}")
            existing_event = await db.fetchrow("SELECT * FROM processed_webhooks WHERE event_id = $1", event_id)
            if existing_event:
                return JSONResponse({"message": "Event already processed"}, status_code=200)
        except Exception as e:
            print(f"Error in idempotency check: {e}") # Add this for debugging
            raise HTTPException(status_code=500, detail=f"Error in idempotency check: {e}")

        print("existing satement: ", existing_event)
        if existing_event:
            return JSONResponse({"message": "Event already processed"}, status_code=200) # Or 204 No Content

        print("event_type choosing: ", event_type)
        # Process the event based on its type
        if event_type == "user.created":
            await create_user(db, data)
        else:
            print(f"Unhandled event type: {event_type}")
            return JSONResponse({"message": f"Unhandled event type: {event_type}"}, status_code=200)

        print("after user functions")
        # Mark the event as processed
        await db.execute("INSERT INTO processed_webhooks (event_id) VALUES ($1)", event_id)
        return JSONResponse({"message": "Webhook processed successfully"}, status_code=200)

    except Exception as e:
        print(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing webhook: {e}")

async def create_user(db, user_data: Dict):
    """Creates a new user in the database."""
    print("create user data:", user_data)
    try:
        # Extract relevant data from the user_data dictionary
        user_id = user_data['id']
        print("user_id: ", user_id)
        email = user_data['email_addresses'][0]['email_address']  # Get the primary email
        print("email: ", email)
        first_name = user_data.get('first_name')  # Use .get() for optional fields
        print("first name: ", first_name)
        last_name = user_data.get('last_name')
        print ("last name: ", last_name)
        profile_image_url = user_data.get('profile_image_url')
        print("profile_image_url: ", profile_image_url)

        await db.execute('''
            INSERT INTO users (id, email, first_name, last_name, profile_image_url)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id) DO NOTHING  -- Handle potential duplicates
        ''', user_id, email, first_name, last_name, profile_image_url)
        print(f"User created: {user_id}")

    except Exception as e:
        print(f"Error creating user: {e}")
        raise  # Re-raise the exception to be caught by the main webhook handler

# --- Database Schema (Add the 'users' table and 'processed_webhooks' table) ---
async def create_tables(db):
    """Creates the necessary database tables."""
    async with db.acquire() as connection:
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                first_name TEXT,
                last_name TEXT,
                profile_image_url TEXT
            )
        ''')
        # Create a table to track processed webhook events (for idempotency)
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS processed_webhooks (
                event_id TEXT PRIMARY KEY
            )
        ''')
        print("users and processed_webhooks tables created (if they didn't exist).")

# --- Event Handlers (Database Connection)---
@app.on_event("startup")
async def startup():
    await init_db(app)
    db = await get_db_pool()
    await create_tables(db)

@app.on_event("shutdown")
async def shutdown():
    await close_db(app)  # Ensure the pool is closed

# --- Include Routers ---
app.include_router(raven.router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Get PORT from env, default to 8080
    uvicorn.run(app, host="0.0.0.0", port=port)
    
# Setup structured logging
logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Webhooks"])

@router.post("/webhooks/sieve/autocrop")
async def receive_sieve_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    clips_repo = Depends(get_clips_repository),
    video_service_instance: VideoService = Depends(get_video_service)
):
    """
    Handles webhooks from Sieve for autocrop operations.
    Refactored to align with updated ClipsRepository methods for transactional integrity.
    """
    klair_clip_id_associated = None
    job_id_associated = None
    user_id_associated = None
    sieve_job_id_from_body = None

    try:
        clip_id_from_query = request.query_params.get("clip_id")

        payload = await request.json()
        body = payload.get("body", {})
        sieve_job_id_from_body = body.get("job_id")
        webhook_status = body.get("status")
        outputs = body.get("outputs")
        error_message_from_sieve = body.get("error", "")

        logger.info("Sieve autocrop webhook received", payload_body=body, sieve_job_id_from_body=sieve_job_id_from_body, webhook_status=webhook_status, clip_id_from_query=clip_id_from_query)

        if not sieve_job_id_from_body:
            logger.error("No sieve_job_id found in Sieve webhook payload body.", payload=payload)
            raise HTTPException(status_code=400, detail="Missing sieve_job_id in webhook payload body")

        async with clips_repo.db_pool.acquire() as conn:
            async with conn.transaction():
                klair_clip_row = None

                # 1. Try by clip_id_from_query
                if clip_id_from_query:
                    klair_clip_row = await clips_repo.get_clip_by_id_for_update(clip_id_from_query, conn=conn)
                    if klair_clip_row:
                        logger.info(f"Found clip {clip_id_from_query} by query parameter for update.")
                        # If it's a processing webhook and sieve_job_id in DB is missing or different, update it.
                        if webhook_status == "processing" and (not klair_clip_row.get("sieve_job_id") or klair_clip_row.get("sieve_job_id") != sieve_job_id_from_body):
                            await clips_repo.update_clip_sieve_job_id(clip_id_from_query, sieve_job_id_from_body, conn=conn)
                            logger.info(f"Updated clip {clip_id_from_query} with Sieve job ID {sieve_job_id_from_body} (matched by query clip_id).")
                            klair_clip_row = await clips_repo.get_clip_by_id_for_update(clip_id_from_query, conn=conn)
                    else:
                        logger.warning(f"Clip ID {clip_id_from_query} from query params not found.")

                # 2. If not found, try by sieve_job_id_from_body
                if not klair_clip_row:
                    klair_clip_row = await clips_repo.get_clip_by_sieve_job_id_for_update(sieve_job_id_from_body, conn=conn)
                    if klair_clip_row:
                        logger.info(f"Found clip {klair_clip_row['id']} by sieve_job_id {sieve_job_id_from_body} from webhook body for update.")
                    else:
                        logger.info(f"No clip found directly by sieve_job_id {sieve_job_id_from_body}.")

                # 3. If still not found AND it's a 'processing' webhook, try to associate with the most recent pending clip
                if not klair_clip_row and webhook_status == "processing":
                    logger.info(f"Attempting to find and assign a pending clip for Sieve job ID {sieve_job_id_from_body} (status: 'processing').")
                    pending_clip_to_assign = await clips_repo.find_pending_clip_for_sieve(conn=conn)
                    if pending_clip_to_assign:
                        await clips_repo.update_clip_sieve_job_id(pending_clip_to_assign["id"], sieve_job_id_from_body, conn=conn)
                        logger.info(f"Associated Sieve job ID {sieve_job_id_from_body} with pending clip {pending_clip_to_assign['id']}.")
                        klair_clip_row = await clips_repo.get_clip_by_id_for_update(pending_clip_to_assign["id"], conn=conn)
                    else:
                        logger.warning(f"No suitable pending clip found to associate with Sieve job ID {sieve_job_id_from_body}.")

                if not klair_clip_row:
                    logger.error(f"No Klair clip could be definitively associated with Sieve job ID: {sieve_job_id_from_body}. Query Param Clip ID: {clip_id_from_query}")
                    return {"status": "error", "message": f"No Klair clip found for Sieve job ID {sieve_job_id_from_body}"}

                klair_clip_id_associated = klair_clip_row["id"]
                job_id_associated = klair_clip_row["job_id"]
                user_id_associated = klair_clip_row["user_id"]

                if webhook_status == "processing":
                    await clips_repo.update_clip_status(klair_clip_id_associated, "sieve_processing", conn=conn)
                    logger.info("Klair clip status updated to sieve_processing", klair_clip_id=klair_clip_id_associated, sieve_job_id=sieve_job_id_from_body)
                    return {"status": "sieve_job_id and status recorded", "klair_clip_id": klair_clip_id_associated}

                elif webhook_status == "failed":
                    error_to_log = error_message_from_sieve or "Sieve job failed with no specific error message."
                    await clips_repo.update_clip_status(klair_clip_id_associated, "sieve_failed", error_to_log, conn=conn)
                    logger.error(f"Sieve job failed: {error_to_log}", klair_clip_id=klair_clip_id_associated, sieve_job_id=sieve_job_id_from_body)
                    return {"status": "error", "message": f"Sieve job {sieve_job_id_from_body} failed: {error_to_log}", "klair_clip_id": klair_clip_id_associated}

                elif webhook_status == "finished":
                    sieve_output_video_url = None
                    if outputs and isinstance(outputs, list) and len(outputs) > 0:
                        for output_item in outputs:
                            if isinstance(output_item, dict):
                                if output_item.get("type") == "sieve.File" and isinstance(output_item.get("data"), list):
                                    for data_item in output_item.get("data", []):
                                        if data_item.get("Key") == "url":
                                            sieve_output_video_url = data_item.get("Value")
                                            break
                                elif output_item.get("video_url") and isinstance(output_item.get("video_url"), str):
                                    sieve_output_video_url = output_item.get("video_url")
                                    break
                                elif output_item.get("url") and isinstance(output_item.get("url"), str) and (".mp4" in output_item.get("url") or ".mov" in output_item.get("url")):
                                    sieve_output_video_url = output_item.get("url")
                                    break
                            if sieve_output_video_url: break

                    if not sieve_output_video_url:
                        logger.error("No video URL found in Sieve 'finished' webhook outputs.", klair_clip_id=klair_clip_id_associated, sieve_job_id=sieve_job_id_from_body, outputs=outputs)
                        await clips_repo.update_clip_status(klair_clip_id_associated, "sieve_failed_output", "No video URL in Sieve outputs", conn=conn)
                        return {"status": "error", "message": "No video URL in Sieve 'finished' webhook outputs", "klair_clip_id": klair_clip_id_associated}

                    await clips_repo.update_clip_download_url_and_status(klair_clip_id_associated, sieve_output_video_url, "pending_watermark", conn=conn)
                    logger.info("Klair clip download_url and status updated to pending_watermark", klair_clip_id=klair_clip_id_associated, sieve_job_id=sieve_job_id_from_body, sieve_video_url=sieve_output_video_url)

                    # Now check Sieve output metadata for errors before watermarking
                    sieve_job_metadata = body.get("metadata", {})
                    sieve_job_error_message = sieve_job_metadata.get("message") # Example path to error

                    if sieve_job_error_message and "failed" in sieve_job_error_message.lower():
                        logger.error(f"Sieve job reported failure in its metadata: {sieve_job_error_message}", 
                                     klair_clip_id=klair_clip_id_associated, sieve_job_id=sieve_job_id_from_body)
                        # Update clip status to reflect Sieve processing failure
                        await clips_repo.update_clip_status(klair_clip_id_associated, AnalysisStatus.FAILED_SIEVE_PROCESSING.value, sieve_job_error_message[:1000], conn=conn)
                        # Do NOT schedule watermarking for this failed clip
                        return {"status": "sieve_job_reported_failure", "message": sieve_job_error_message, "klair_clip_id": klair_clip_id_associated}
                    else:
                        # Proceed with watermarking if no Sieve metadata error
                        background_tasks.add_task(
                            video_service_instance.watermark_and_upload_sieve_video,
                            sieve_video_url=sieve_output_video_url,
                            klair_clip_id=klair_clip_id_associated,
                            user_id=user_id_associated,
                            job_id=job_id_associated
                        )
                        logger.info("Scheduled background task to watermark and upload Sieve video", klair_clip_id=klair_clip_id_associated)
                        return {"status": "webhook processed successfully, watermarking initiated", "klair_clip_id": klair_clip_id_associated}

                else:
                    logger.warning("Unhandled Sieve webhook status.", klair_clip_id=klair_clip_id_associated, sieve_job_id=sieve_job_id_from_body, webhook_status=webhook_status, payload=payload)
                    return {"status": "unhandled_webhook_status", "received_status": webhook_status, "klair_clip_id": klair_clip_id_associated}

    except HTTPException as http_exc:
        raise
    except Exception as e:
        logger.error(f"Error processing Sieve webhook: {str(e)}", exc_info=True,
                    klair_clip_id=klair_clip_id_associated, job_id=job_id_associated, sieve_job_id=sieve_job_id_from_body, user_id=user_id_associated)
        
        if klair_clip_id_associated:
            try:
                clips_repo_fallback = await get_clips_repository()
                await clips_repo_fallback.update_clip_status(klair_clip_id_associated, "webhook_error", f"Webhook processing error: {str(e)[:100]}")
                logger.info(f"Marked clip {klair_clip_id_associated} as webhook_error due to exception.")
            except Exception as db_update_err:
                logger.error(f"Failed to update clip {klair_clip_id_associated} status to webhook_error after main exception: {db_update_err}", exc_info=True)
        
        raise HTTPException(status_code=500, detail=f"Internal Server Error processing webhook: {str(e)[:200]}") 