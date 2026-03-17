import httpx
import structlog
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.enums import PipelineStage
from core.models import IntakeRecord, QualificationResult

logger = structlog.get_logger()
settings = get_settings()

GHL_BASE_URL = "https://services.leadconnectorhq.com"


class GHLClient:
    def __init__(self) -> None:
        self.api_key: str = settings.ghl_api_key
        self.location_id: str = settings.ghl_location_id
        self.headers: dict = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28",
        }

    # ------------------------------------------------------------------
    # Contact management
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_contact_by_phone(
        self, phone_number: str
    ) -> Optional[dict]:
        """
        Look up a contact by phone number.
        Returns the contact dict if found, None if not found.
        """
        params = {
            "locationId": self.location_id,
            "phone": phone_number,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GHL_BASE_URL}/contacts/search/duplicate",
                headers=self.headers,
                params=params,
                timeout=10.0,
            )
            if response.status_code == 404:
                logger.info(
                    "ghl_contact_not_found",
                    phone_number=phone_number,
                )
                return None
            response.raise_for_status()
            data = response.json()
            contact = data.get("contact")
            logger.info(
                "ghl_contact_found",
                phone_number=phone_number,
                contact_id=contact.get("id") if contact else None,
            )
            return contact

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_contact(
        self,
        phone_number: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        tags: Optional[list] = None,
        custom_fields: Optional[dict] = None,
    ) -> dict:
        """Create a new contact in GoHighLevel."""
        payload: dict = {
            "locationId": self.location_id,
            "phone": phone_number,
        }
        if name:
            parts = name.strip().split(" ", 1)
            payload["firstName"] = parts[0]
            if len(parts) > 1:
                payload["lastName"] = parts[1]
        if email:
            payload["email"] = email
        if tags:
            payload["tags"] = tags
        if custom_fields:
            payload["customFields"] = [
                {"key": k, "field_value": v}
                for k, v in custom_fields.items()
            ]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GHL_BASE_URL}/contacts/",
                headers=self.headers,
                json=payload,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            contact = data.get("contact", data)
            logger.info(
                "ghl_contact_created",
                phone_number=phone_number,
                contact_id=contact.get("id"),
            )
            return contact

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def update_contact(
        self,
        contact_id: str,
        updates: dict,
    ) -> dict:
        """Update an existing contact record."""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{GHL_BASE_URL}/contacts/{contact_id}",
                headers=self.headers,
                json=updates,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "ghl_contact_updated",
                contact_id=contact_id,
            )
            return data

    async def get_or_create_contact(
        self,
        phone_number: str,
        name: Optional[str] = None,
    ) -> dict:
        """
        Look up a contact by phone. Create one if not found.
        Returns the contact dict either way.
        """
        contact = await self.get_contact_by_phone(phone_number)
        if contact:
            return contact
        return await self.create_contact(phone_number=phone_number, name=name)

    # ------------------------------------------------------------------
    # Tag management
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def add_tags(
        self,
        contact_id: str,
        tags: list[str],
    ) -> dict:
        """Add tags to a contact record."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GHL_BASE_URL}/contacts/{contact_id}/tags",
                headers=self.headers,
                json={"tags": tags},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "ghl_tags_added",
                contact_id=contact_id,
                tags=tags,
            )
            return data

    # ------------------------------------------------------------------
    # Pipeline stage management
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def update_pipeline_stage(
        self,
        contact_id: str,
        pipeline_id: str,
        stage_id: str,
    ) -> dict:
        """Move a contact to a new pipeline stage."""
        payload = {
            "pipelineId": pipeline_id,
            "pipelineStageId": stage_id,
            "status": "open",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GHL_BASE_URL}/opportunities/",
                headers=self.headers,
                json={
                    "pipelineId": pipeline_id,
                    "locationId": self.location_id,
                    "contactId": contact_id,
                    "pipelineStageId": stage_id,
                    "status": "open",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "ghl_pipeline_stage_updated",
                contact_id=contact_id,
                stage_id=stage_id,
            )
            return data

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def add_note(
        self,
        contact_id: str,
        note_body: str,
        user_id: Optional[str] = None,
    ) -> dict:
        """Add a note to a contact record."""
        payload: dict = {
            "body": note_body,
            "contactId": contact_id,
        }
        if user_id:
            payload["userId"] = user_id

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GHL_BASE_URL}/contacts/{contact_id}/notes",
                headers=self.headers,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "ghl_note_added",
                contact_id=contact_id,
            )
            return data

    # ------------------------------------------------------------------
    # Full intake sync (combines multiple operations)
    # ------------------------------------------------------------------

    async def sync_intake_to_contact(
        self,
        contact_id: str,
        intake: IntakeRecord,
        qualification: QualificationResult,
    ) -> dict:
        """
        Write the complete intake and qualification data to a
        GoHighLevel contact record in a single coordinated update.
        """
        tags = [
            f"case-type:{intake.case_type.value}",
            f"urgency:{intake.urgency_level.value}",
            f"language:{intake.language.value}",
            f"lead-score:{qualification.label.value}",
        ]

        if intake.is_detained:
            tags.append("detained")
        if qualification.requires_escalation:
            tags.append("escalation-required")
        if intake.court_involvement:
            tags.append("court-involvement")

        await self.add_tags(contact_id, tags)

        note = (
            f"AI Intake Summary\n"
            f"{'=' * 40}\n"
            f"Name: {intake.name}\n"
            f"Language: {intake.language.value.upper()}\n"
            f"Country of Origin: {intake.country_of_origin}\n"
            f"Entry Date: {intake.entry_date}\n"
            f"Family Status: {intake.family_status}\n"
            f"Case Type: {intake.case_type.value}\n"
            f"Court Involvement: {intake.court_involvement}\n"
            f"Detained: {intake.is_detained}\n"
            f"Urgency: {intake.urgency_level.value.upper()}\n"
            f"\nQualification Score: {qualification.score}/100 "
            f"({qualification.label.value.upper()})\n"
            f"\nAttorney Brief:\n{qualification.summary}\n"
            f"\nEscalation Required: {qualification.requires_escalation}\n"
        )
        if qualification.escalation_reason:
            note += f"Escalation Reason: {qualification.escalation_reason}\n"

        await self.add_note(contact_id, note)

        logger.info(
            "ghl_intake_synced",
            contact_id=contact_id,
            lead_id=intake.lead_id,
            score=qualification.score,
        )

        return {"contact_id": contact_id, "tags_added": tags}

    # ------------------------------------------------------------------
    # Calendar availability
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_calendar_slots(
        self,
        calendar_id: str,
        start_date: str,
        end_date: str,
        timezone: str = "America/New_York",
    ) -> list:
        """
        Fetch available appointment slots from a GHL calendar.
        start_date and end_date format: YYYY-MM-DD
        """
        params = {
            "calendarId": calendar_id,
            "startDate": start_date,
            "endDate": end_date,
            "timezone": timezone,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GHL_BASE_URL}/calendars/slots",
                headers=self.headers,
                params=params,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            slots = data.get("slots", [])
            logger.info(
                "ghl_calendar_slots_fetched",
                calendar_id=calendar_id,
                slot_count=len(slots),
            )
            return slots


# Singleton instance
ghl_client = GHLClient()