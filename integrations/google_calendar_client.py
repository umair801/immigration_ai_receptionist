import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.models import AppointmentSlot

logger = structlog.get_logger()
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
FIRM_TIMEZONE = "America/New_York"
CONSULTATION_DURATION_MINUTES = 30


class GoogleCalendarClient:
    def __init__(self) -> None:
        self.calendar_id: str = settings.google_calendar_id
        self.service_account_json: str = settings.google_service_account_json
        self._service = None

    def _get_service(self):
        """
        Build and cache the Google Calendar service client.
        Uses a service account so no OAuth flow is needed.
        """
        if self._service is None:
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_json,
                scopes=SCOPES,
            )
            self._service = build(
                "calendar", "v3", credentials=credentials, cache_discovery=False
            )
            logger.info("google_calendar_service_initialized")
        return self._service

    # ------------------------------------------------------------------
    # Slot availability
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def get_available_slots(
        self,
        days_ahead: int = 5,
        slots_to_return: int = 3,
        business_hours_start: int = 9,
        business_hours_end: int = 17,
    ) -> list[dict]:
        """
        Return the next N available consultation slots within business hours.
        Checks existing calendar events to avoid double-booking.
        """
        service = self._get_service()
        tz = ZoneInfo(FIRM_TIMEZONE)

        now = datetime.now(tz)
        search_end = now + timedelta(days=days_ahead)

        # Fetch all existing events in the window
        try:
            events_result = service.events().list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat(),
                timeMax=search_end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            existing_events = events_result.get("items", [])
        except HttpError as e:
            logger.error("google_calendar_fetch_error", error=str(e))
            raise

        # Build a set of busy time ranges
        busy_slots: list[tuple] = []
        for event in existing_events:
            start = event.get("start", {}).get("dateTime")
            end = event.get("end", {}).get("dateTime")
            if start and end:
                busy_slots.append((
                    datetime.fromisoformat(start),
                    datetime.fromisoformat(end),
                ))

        # Generate candidate slots every 30 minutes during business hours
        available: list[dict] = []
        candidate = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        while candidate < search_end and len(available) < slots_to_return:
            # Skip outside business hours
            if not (business_hours_start <= candidate.hour < business_hours_end):
                candidate += timedelta(minutes=30)
                continue

            # Skip weekends
            if candidate.weekday() >= 5:
                candidate += timedelta(days=1)
                candidate = candidate.replace(
                    hour=business_hours_start, minute=0
                )
                continue

            slot_end = candidate + timedelta(minutes=CONSULTATION_DURATION_MINUTES)

            # Check for conflicts
            conflict = any(
                not (slot_end <= busy_start or candidate >= busy_end)
                for busy_start, busy_end in busy_slots
            )

            if not conflict:
                available.append({
                    "start": candidate.isoformat(),
                    "end": slot_end.isoformat(),
                    "display": candidate.strftime("%A, %B %d at %I:%M %p %Z"),
                })

            candidate += timedelta(minutes=30)

        logger.info(
            "google_calendar_slots_available",
            count=len(available),
            days_ahead=days_ahead,
        )
        return available

    # ------------------------------------------------------------------
    # Appointment creation
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def create_appointment(
        self,
        slot: AppointmentSlot,
        contact_name: str,
        contact_phone: str,
        case_summary: str,
        attorney_email: Optional[str] = None,
    ) -> dict:
        """
        Create a confirmed consultation appointment in Google Calendar.
        Called after payment is confirmed.
        """
        service = self._get_service()

        attendees = []
        if attorney_email:
            attendees.append({"email": attorney_email})

        event_body = {
            "summary": f"Immigration Consultation: {contact_name}",
            "description": (
                f"Contact: {contact_name}\n"
                f"Phone: {contact_phone}\n"
                f"Case Summary: {case_summary}\n"
                f"Booked via AI Receptionist"
            ),
            "start": {
                "dateTime": slot.start_time.isoformat(),
                "timeZone": FIRM_TIMEZONE,
            },
            "end": {
                "dateTime": slot.end_time.isoformat(),
                "timeZone": FIRM_TIMEZONE,
            },
            "attendees": attendees,
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 1440},
                    {"method": "popup", "minutes": 30},
                ],
            },
            "status": "confirmed",
        }

        try:
            created_event = service.events().insert(
                calendarId=self.calendar_id,
                body=event_body,
                sendUpdates="all" if attendees else "none",
            ).execute()

            logger.info(
                "google_calendar_appointment_created",
                event_id=created_event.get("id"),
                contact_name=contact_name,
                start=slot.start_time.isoformat(),
            )
            return created_event

        except HttpError as e:
            logger.error(
                "google_calendar_create_error",
                error=str(e),
                contact_name=contact_name,
            )
            raise

    # ------------------------------------------------------------------
    # Appointment cancellation
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def cancel_appointment(self, event_id: str) -> bool:
        """Cancel an existing calendar event by its Google event ID."""
        service = self._get_service()
        try:
            service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
            logger.info(
                "google_calendar_appointment_cancelled",
                event_id=event_id,
            )
            return True
        except HttpError as e:
            logger.error(
                "google_calendar_cancel_error",
                event_id=event_id,
                error=str(e),
            )
            return False

    # ------------------------------------------------------------------
    # Event lookup
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def get_event(self, event_id: str) -> Optional[dict]:
        """Fetch a calendar event by ID."""
        service = self._get_service()
        try:
            event = service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
            logger.info("google_calendar_event_fetched", event_id=event_id)
            return event
        except HttpError as e:
            logger.error(
                "google_calendar_get_error",
                event_id=event_id,
                error=str(e),
            )
            return None


# Singleton instance
google_calendar_client = GoogleCalendarClient()