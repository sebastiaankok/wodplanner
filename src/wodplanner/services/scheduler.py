"""Scheduler service for executing auto-signups at the right time."""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from wodplanner.api.client import WodAppClient, WodAppError
from wodplanner.models.auth import AuthSession
from wodplanner.models.queue import QueuedSignup, QueueStatus
from wodplanner.services.queue import QueueService

logger = logging.getLogger(__name__)


class SignupScheduler:
    """Scheduler for auto-signup jobs."""

    def __init__(self, queue_service: QueueService) -> None:
        self.queue_service = queue_service
        self.scheduler = BackgroundScheduler()
        self._started = False

    def start(self) -> None:
        """Start the scheduler and schedule all pending signups."""
        if self._started:
            return

        self.scheduler.start()
        self._started = True
        logger.info("Signup scheduler started")

        # Schedule all pending signups
        self._schedule_pending()

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("Signup scheduler stopped")

    def _schedule_pending(self) -> None:
        """Schedule all pending signups from the queue."""
        pending = self.queue_service.get_pending()
        for signup in pending:
            self._schedule_signup(signup)

    def _schedule_signup(self, signup: QueuedSignup) -> None:
        """Schedule a single signup job."""
        job_id = f"signup_{signup.id}"

        # Check if job already exists
        if self.scheduler.get_job(job_id):
            logger.debug(f"Job {job_id} already scheduled")
            return

        # If signup time has passed, execute immediately
        now = datetime.now()
        run_at = signup.signup_opens_at

        if run_at <= now:
            logger.info(f"Signup {signup.id} is already open, executing immediately")
            self._execute_signup(signup.id)
            return

        # Schedule for the future - add a small buffer (2 seconds) to ensure it's open
        run_at = run_at + timedelta(seconds=2)

        self.scheduler.add_job(
            self._execute_signup,
            trigger=DateTrigger(run_date=run_at),
            args=[signup.id],
            id=job_id,
            name=f"Signup for {signup.appointment_name}",
            replace_existing=True,
        )

        self.queue_service.update_status(signup.id, QueueStatus.SCHEDULED)
        logger.info(
            f"Scheduled signup {signup.id} for {signup.appointment_name} at {run_at}"
        )

    def _create_client_for_signup(self, signup: QueuedSignup) -> WodAppClient | None:
        """Create a WodAppClient from stored signup credentials."""
        if not signup.user_token or not signup.user_id:
            logger.error(f"Signup {signup.id} missing user credentials")
            return None

        # Create a minimal session with the stored token
        # Note: We don't have all session data, but token and user_id are enough for API calls
        session = AuthSession(
            token=signup.user_token,
            user_id=signup.user_id,
            username="",  # Not needed for API calls
            firstname="",  # Not needed for API calls
            gym_id=0,  # Will be determined from token
            gym_name="",  # Not needed for API calls
            agenda_id=None,  # Will need to fetch this
        )

        client = WodAppClient.from_session(session)

        # We need to fetch the agenda_id for this client to work properly
        # The token contains the gym info, so we can call getAgendas
        try:
            client._fetch_agenda_id()
        except WodAppError as e:
            logger.error(f"Failed to fetch agenda for signup {signup.id}: {e}")
            return None

        return client

    def _execute_signup(self, signup_id: int) -> None:
        """Execute the signup for a queued item."""
        signup = self.queue_service.get(signup_id)
        if not signup:
            logger.error(f"Signup {signup_id} not found")
            return

        if signup.status not in (QueueStatus.PENDING, QueueStatus.SCHEDULED):
            logger.info(f"Signup {signup_id} is {signup.status}, skipping")
            return

        logger.info(f"Executing signup for {signup.appointment_name} (ID: {signup_id})")

        # Create client from stored credentials
        client = self._create_client_for_signup(signup)
        if not client:
            self.queue_service.update_status(
                signup_id,
                QueueStatus.FAILED,
                "Session expired or invalid - please log in and queue again",
            )
            return

        try:
            # Attempt to subscribe
            result = client.subscribe(
                signup.appointment_id,
                signup.date_start,
                signup.date_end,
            )

            if result.subscribedWithSuccess:
                self.queue_service.update_status(
                    signup_id,
                    QueueStatus.COMPLETED,
                    result.notice,
                )
                logger.info(f"Successfully signed up for {signup.appointment_name}")
            else:
                # Subscription failed, try waiting list
                logger.info(f"Signup failed, trying waiting list: {result.notice}")
                self._try_waitinglist(client, signup, result.notice)

        except WodAppError as e:
            error_msg = str(e)
            logger.warning(f"Signup error: {error_msg}")

            # Check if it's a "class full" error - try waiting list
            if "vol" in error_msg.lower() or "full" in error_msg.lower():
                self._try_waitinglist(client, signup, error_msg)
            else:
                self.queue_service.update_status(
                    signup_id,
                    QueueStatus.FAILED,
                    error_msg,
                )

        except Exception as e:
            logger.exception(f"Unexpected error during signup: {e}")
            self.queue_service.update_status(
                signup_id,
                QueueStatus.FAILED,
                str(e),
            )
        finally:
            client.close()

    def _try_waitinglist(
        self, client: WodAppClient, signup: QueuedSignup, original_error: str
    ) -> None:
        """Try to add to waiting list when signup fails."""
        try:
            result = client.subscribe_waitinglist(
                signup.appointment_id,
                signup.date_start,
                signup.date_end,
            )
            self.queue_service.update_status(
                signup.id,
                QueueStatus.WAITLISTED,
                f"Class full, added to waiting list: {result.notice}",
            )
            logger.info(f"Added to waiting list for {signup.appointment_name}")

        except WodAppError as e:
            self.queue_service.update_status(
                signup.id,
                QueueStatus.FAILED,
                f"Signup failed ({original_error}), waiting list also failed: {e}",
            )
            logger.error(f"Failed to add to waiting list: {e}")

    def add_signup(self, signup: QueuedSignup) -> QueuedSignup:
        """Add a new signup to the queue and schedule it."""
        signup = self.queue_service.add(signup)
        if self._started:
            self._schedule_signup(signup)
        return signup

    def cancel_signup(self, signup_id: int) -> bool:
        """Cancel a scheduled signup."""
        job_id = f"signup_{signup_id}"

        # Remove the scheduled job if it exists
        job = self.scheduler.get_job(job_id)
        if job:
            self.scheduler.remove_job(job_id)

        # Update the queue
        return self.queue_service.cancel(signup_id)

    def get_scheduled_jobs(self) -> list[dict]:
        """Get info about all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs
