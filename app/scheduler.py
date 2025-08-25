"""
Scheduling system for automated daily celebration checks and message sending.
"""
import logging
import asyncio
from datetime import datetime, time
from typing import Optional
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services import whatsapp_messenger

logger = logging.getLogger(__name__)


class CelebrationScheduler:
    """Manages scheduled tasks for daily celebration checks."""

    def __init__(self):
        """Initialize the scheduler."""
        self.scheduler = AsyncIOScheduler()
        self.timezone = pytz.timezone(settings.timezone)
        self.is_running = False

    async def daily_celebration_job(self):
        """Job that runs daily to check for celebrations and send messages."""
        try:
            logger.info("Starting daily celebration check...")

            # Send daily celebrations
            result = await whatsapp_messenger.send_daily_celebrations()

            if result["success"]:
                logger.info(f"Daily celebration job completed successfully. Sent {result['sent_count']} messages.")
            else:
                logger.error(f"Daily celebration job failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Error in daily celebration job: {e}")

    def setup_daily_schedule(self):
        """Set up the daily schedule for celebration checks."""
        try:
            # Parse the schedule time
            schedule_time_str = settings.schedule_time  # Format: "HH:MM"
            hour, minute = map(int, schedule_time_str.split(':'))

            # Create cron trigger for daily execution
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                timezone=self.timezone
            )

            # Add the job to the scheduler
            self.scheduler.add_job(
                self.daily_celebration_job,
                trigger=trigger,
                id='daily_celebrations',
                name='Daily Celebration Check',
                replace_existing=True
            )

            logger.info(f"Daily celebration job scheduled for {schedule_time_str} {settings.timezone}")

        except Exception as e:
            logger.error(f"Error setting up daily schedule: {e}")
            raise

    def start(self):
        """Start the scheduler."""
        try:
            if not self.is_running:
                self.setup_daily_schedule()
                self.scheduler.start()
                self.is_running = True
                logger.info("Celebration scheduler started successfully")
            else:
                logger.warning("Scheduler is already running")

        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
            raise

    def stop(self):
        """Stop the scheduler."""
        try:
            if self.is_running:
                self.scheduler.shutdown()
                self.is_running = False
                logger.info("Celebration scheduler stopped")
            else:
                logger.warning("Scheduler is not running")

        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")

    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled run time."""
        try:
            job = self.scheduler.get_job('daily_celebrations')
            if job:
                return job.next_run_time
            return None

        except Exception as e:
            logger.error(f"Error getting next run time: {e}")
            return None

    def get_status(self) -> dict:
        """Get scheduler status information."""
        try:
            next_run = self.get_next_run_time()

            return {
                "is_running": self.is_running,
                "next_run_time": next_run.isoformat() if next_run else None,
                "timezone": settings.timezone,
                "schedule_time": settings.schedule_time,
                "job_count": len(self.scheduler.get_jobs())
            }

        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {
                "is_running": False,
                "error": str(e)
            }

    async def run_manual_check(self):
        """Manually trigger a celebration check (for testing)."""
        logger.info("Running manual celebration check...")
        await self.daily_celebration_job()


# Global scheduler instance
celebration_scheduler = CelebrationScheduler()
