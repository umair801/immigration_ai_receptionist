import structlog
from typing import Optional
from datetime import datetime

from core.database import supabase
from core.enums import CallStatus, Language, CallerType
from core.models import CallSession, Lead

logger = structlog.get_logger()


class SessionManager:
    """
    Persists and retrieves CallSession state from Supabase.
    This is the memory layer that keeps conversation state alive
    across multiple Retell AI voice turns.
    """

    async def create_lead(self, lead: Lead) -> Lead:
        """Insert a new lead record into Supabase."""
        data = {
            "id": lead.id,
            "phone_number": lead.phone_number,
            "name": lead.name,
            "email": lead.email,
            "language": lead.language.value,
            "caller_type": lead.caller_type.value,
            "ghl_contact_id": lead.ghl_contact_id,
        }
        result = supabase.table("leads").insert(data).execute()
        logger.info("lead_created", lead_id=lead.id)
        return lead

    async def get_lead_by_phone(self, phone_number: str) -> Optional[Lead]:
        """Look up an existing lead by phone number."""
        result = (
            supabase.table("leads")
            .select("*")
            .eq("phone_number", phone_number)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return Lead(
                id=row["id"],
                phone_number=row["phone_number"],
                name=row.get("name"),
                email=row.get("email"),
                language=Language(row.get("language", "en")),
                caller_type=CallerType(row.get("caller_type", "unknown")),
                ghl_contact_id=row.get("ghl_contact_id"),
            )
        return None

    async def create_session(self, session: CallSession) -> CallSession:
        """Insert a new call session record."""
        data = {
            "id": session.id,
            "call_id": session.call_id,
            "phone_number": session.phone_number,
            "lead_id": session.lead_id,
            "caller_type": session.caller_type.value,
            "language": session.language.value,
            "status": session.status.value,
            "started_at": session.started_at.isoformat(),
        }
        supabase.table("call_sessions").insert(data).execute()
        logger.info("session_created", session_id=session.id, call_id=session.call_id)
        return session

    async def get_session_by_call_id(self, call_id: str) -> Optional[CallSession]:
        """Retrieve a session by Retell call ID."""
        result = (
            supabase.table("call_sessions")
            .select("*")
            .eq("call_id", call_id)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return CallSession(
                id=row["id"],
                call_id=row["call_id"],
                phone_number=row["phone_number"],
                lead_id=row.get("lead_id"),
                caller_type=CallerType(row.get("caller_type", "unknown")),
                language=Language(row.get("language", "en")),
                status=CallStatus(row.get("status", "initiated")),
                intake_id=row.get("intake_id"),
                transcript=row.get("transcript"),
                call_summary=row.get("call_summary"),
                started_at=datetime.fromisoformat(row["started_at"]),
            )
        return None

    async def update_session_status(
        self,
        session_id: str,
        status: CallStatus,
    ) -> None:
        """Update the status field of a call session."""
        supabase.table("call_sessions").update(
            {"status": status.value}
        ).eq("id", session_id).execute()
        logger.info("session_status_updated", session_id=session_id, status=status)

    async def close_session(
        self,
        session_id: str,
        transcript: Optional[str] = None,
        call_summary: Optional[str] = None,
    ) -> None:
        """Mark a session as completed and record the transcript."""
        ended_at = datetime.utcnow()
        updates: dict = {
            "status": CallStatus.COMPLETED.value,
            "ended_at": ended_at.isoformat(),
        }
        if transcript:
            updates["transcript"] = transcript
        if call_summary:
            updates["call_summary"] = call_summary

        supabase.table("call_sessions").update(updates).eq("id", session_id).execute()
        logger.info("session_closed", session_id=session_id)

    async def log_event(
        self,
        event_type: str,
        session_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        event_data: Optional[dict] = None,
    ) -> None:
        """Append an event to the call_logs table."""
        data: dict = {
            "event_type": event_type,
            "call_session_id": session_id,
            "lead_id": lead_id,
            "event_data": event_data or {},
        }
        supabase.table("call_logs").insert(data).execute()


# Singleton instance
session_manager = SessionManager()