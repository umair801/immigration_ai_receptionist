import structlog
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
from datetime import datetime

from core.enums import Language, CallerType, CallStatus
from core.models import Lead, CallSession, WebhookIntakePayload
from core.session_manager import session_manager

logger = structlog.get_logger()
router = APIRouter(prefix="/voice", tags=["voice"])


def detect_language_from_retell(payload: dict) -> Language:
    """
    Detect caller language from Retell webhook payload.
    Checks custom fields and call metadata.
    Defaults to Spanish for Miami market.
    """
    metadata = payload.get("metadata", {})
    lang = metadata.get("language", "")
    if lang == "en":
        return Language.ENGLISH
    if lang == "es":
        return Language.SPANISH

    custom = payload.get("custom_analysis_data", {})
    if custom.get("language") == "en":
        return Language.ENGLISH

    return Language.SPANISH


# ------------------------------------------------------------------
# Retell AI webhook endpoint
# ------------------------------------------------------------------

@router.post("/retell-webhook")
async def retell_webhook(
    request: Request,
    x_retell_signature: Optional[str] = Header(None),
):
    """
    Main webhook receiver for Retell AI call events.
    Handles: call_started, call_analyzed, call_ended
    """
    raw_body = await request.body()

    # Signature verification
    from integrations.retell_client import retell_client
    if x_retell_signature:
        if not retell_client.verify_webhook_signature(raw_body, x_retell_signature):
            logger.warning("retell_webhook_invalid_signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event")
    call_id = payload.get("data", {}).get("call_id", "")

    logger.info(
        "retell_webhook_received",
        event_type=event_type,
        call_id=call_id,
    )

    if event_type == "call_started":
        return await handle_call_started(payload)

    if event_type == "call_analyzed":
        return await handle_call_analyzed(payload)

    if event_type == "call_ended":
        return await handle_call_ended(payload)

    return {"status": "ignored", "event": event_type}


async def handle_call_started(payload: dict) -> dict:
    """
    Triggered when a new inbound call begins.
    Creates a Lead and CallSession in Supabase.
    Checks GoHighLevel to determine if caller is new or existing.
    """
    call_data = payload.get("data", {})
    call_id = call_data.get("call_id", "")
    phone_number = call_data.get("from_number", "")
    language = detect_language_from_retell(call_data)

    # Check if lead already exists
    existing_lead = await session_manager.get_lead_by_phone(phone_number)

    if existing_lead:
        lead = existing_lead
        caller_type = CallerType.EXISTING_CLIENT
        logger.info(
            "retell_existing_lead",
            lead_id=lead.id,
            phone=phone_number,
        )
    else:
        lead = Lead(
            phone_number=phone_number,
            language=language,
            caller_type=CallerType.NEW_LEAD,
        )
        await session_manager.create_lead(lead)
        caller_type = CallerType.NEW_LEAD
        logger.info(
            "retell_new_lead_created",
            lead_id=lead.id,
            phone=phone_number,
        )

    session = CallSession(
        call_id=call_id,
        phone_number=phone_number,
        lead_id=lead.id,
        caller_type=caller_type,
        language=language,
        status=CallStatus.INITIATED,
    )
    await session_manager.create_session(session)

    await session_manager.log_event(
        event_type="call_started",
        session_id=session.id,
        lead_id=lead.id,
        event_data={
            "phone_number": phone_number,
            "language": language.value,
            "caller_type": caller_type.value,
        },
    )

    return {"status": "ok", "session_id": session.id, "lead_id": lead.id}


async def handle_call_analyzed(payload: dict) -> dict:
    """
    Triggered after Retell analyzes the completed call.
    Stores the transcript and call summary.
    """
    call_data = payload.get("data", {})
    call_id = call_data.get("call_id", "")
    transcript = call_data.get("transcript", "")
    call_analysis = call_data.get("call_analysis", {})
    summary = call_analysis.get("call_summary", "")

    session = await session_manager.get_session_by_call_id(call_id)
    if not session:
        logger.warning("retell_analyzed_session_not_found", call_id=call_id)
        return {"status": "session_not_found"}

    await session_manager.close_session(
        session_id=session.id,
        transcript=transcript,
        call_summary=summary,
    )

    await session_manager.log_event(
        event_type="call_analyzed",
        session_id=session.id,
        lead_id=session.lead_id,
        event_data={"transcript_length": len(transcript), "has_summary": bool(summary)},
    )

    logger.info(
        "retell_call_analyzed",
        call_id=call_id,
        session_id=session.id,
        transcript_length=len(transcript),
    )

    return {"status": "ok"}


async def handle_call_ended(payload: dict) -> dict:
    """
    Triggered when the call disconnects.
    Updates session status and logs the end event.
    """
    call_data = payload.get("data", {})
    call_id = call_data.get("call_id", "")
    end_reason = call_data.get("disconnection_reason", "unknown")

    session = await session_manager.get_session_by_call_id(call_id)
    if not session:
        logger.warning("retell_ended_session_not_found", call_id=call_id)
        return {"status": "session_not_found"}

    final_status = (
        CallStatus.ABANDONED
        if end_reason in ["caller_hangup_during_greeting", "no_audio"]
        else CallStatus.COMPLETED
    )

    await session_manager.update_session_status(session.id, final_status)

    await session_manager.log_event(
        event_type="call_ended",
        session_id=session.id,
        lead_id=session.lead_id,
        event_data={"end_reason": end_reason, "final_status": final_status.value},
    )

    logger.info(
        "retell_call_ended",
        call_id=call_id,
        end_reason=end_reason,
        final_status=final_status,
    )

    return {"status": "ok"}


# ------------------------------------------------------------------
# Demo intake webhook
# ------------------------------------------------------------------

@router.post("/intake-webhook")
async def intake_webhook(payload: WebhookIntakePayload):
    """
    Demo endpoint: receives intake data posted by Retell after a call.
    Writes name, reason, and language to GoHighLevel.
    Used for the demo recording sent to the client.
    """
    logger.info(
        "intake_webhook_received",
        call_id=payload.call_id,
        phone=payload.phone_number,
        language=payload.language,
    )

    from agents.crm_sync_agent import crm_sync_agent

    result = await crm_sync_agent.sync_minimal(
        phone_number=payload.phone_number,
        name=payload.name,
        reason=payload.reason_for_calling,
        language=payload.language.value,
    )

    await session_manager.log_event(
        event_type="intake_webhook_received",
        event_data={
            "call_id": payload.call_id,
            "phone": payload.phone_number,
            "name": payload.name,
            "language": payload.language.value,
        },
    )

    return {
        "status": "ok",
        "ghl_contact_id": result.get("contact_id"),
        "message": "Intake data synced to CRM",
    }


# ------------------------------------------------------------------
# Outbound call trigger
# ------------------------------------------------------------------

@router.post("/trigger-outbound")
async def trigger_outbound(request: Request):
    """
    GoHighLevel webhook trigger for outbound calls.
    Called when a new lead enters a configured pipeline stage.
    """
    payload = await request.json()

    logger.info(
        "outbound_trigger_received",
        payload_keys=list(payload.keys()),
    )

    from agents.outbound_caller_agent import outbound_caller_agent

    try:
        lead, session = await outbound_caller_agent.process_ghl_webhook(payload)
        return {
            "status": "ok",
            "lead_id": lead.id,
            "session_id": session.id,
            "phone": lead.phone_number,
        }
    except ValueError as e:
        logger.error("outbound_trigger_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))