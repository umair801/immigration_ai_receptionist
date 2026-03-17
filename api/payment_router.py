import structlog
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

from core.session_manager import session_manager

logger = structlog.get_logger()
router = APIRouter(prefix="/payment", tags=["payment"])


@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """
    Receives and processes Stripe webhook events.
    Verifies signature, parses event type, and triggers
    the payment confirmation agent on successful payment.
    """
    raw_body = await request.body()

    if not stripe_signature:
        logger.warning("stripe_webhook_missing_signature")
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    from integrations.stripe_client import stripe_client

    try:
        event = stripe_client.verify_webhook(raw_body, stripe_signature)
    except ValueError as e:
        logger.error("stripe_webhook_verification_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type", "")
    logger.info("stripe_webhook_received", event_type=event_type)

    # Only process payment completion events
    if event_type not in [
        "payment_intent.succeeded",
        "checkout.session.completed",
    ]:
        return {"status": "ignored", "event_type": event_type}

    return await handle_payment_confirmed(event)


async def handle_payment_confirmed(event: dict) -> dict:
    """
    Orchestrates the post-payment confirmation flow:
    1. Parse payment metadata from Stripe event
    2. Load the appointment from Supabase
    3. Run payment confirmation agent
    4. Update Supabase records
    5. Log the event
    """
    from agents.payment_confirmation_agent import payment_confirmation_agent
    from core.database import supabase

    payment_agent = payment_confirmation_agent
    payment_info = payment_agent.parse_stripe_event(event)

    if not payment_info:
        return {"status": "no_payment_info"}

    appointment_id = payment_info.get("appointment_id")
    lead_id = payment_info.get("lead_id")
    language = "es"  # Default to Spanish; override from lead record if available

    # Load appointment from Supabase
    appointment = None
    if appointment_id:
        result = (
            supabase.table("appointment_slots")
            .select("*")
            .eq("id", appointment_id)
            .limit(1)
            .execute()
        )
        if result.data:
            from core.models import AppointmentSlot
            from core.enums import AppointmentStatus
            from datetime import datetime

            row = result.data[0]
            appointment = AppointmentSlot(
                id=row["id"],
                lead_id=row["lead_id"],
                start_time=datetime.fromisoformat(row["start_time"]),
                end_time=datetime.fromisoformat(row["end_time"]),
                status=AppointmentStatus(row.get("status", "pending_payment")),
                stripe_payment_link=row.get("stripe_payment_link"),
                google_event_id=row.get("google_event_id"),
            )

    # Load lead language preference
    if lead_id:
        lead = await session_manager.get_lead_by_phone(
            payment_info.get("contact_phone", "")
        )
        if lead:
            language = lead.language.value

    # Load GHL contact ID
    ghl_contact_id = None
    if lead_id:
        result = (
            supabase.table("leads")
            .select("ghl_contact_id")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        if result.data:
            ghl_contact_id = result.data[0].get("ghl_contact_id")

    # Run confirmation flow
    payment_record = await payment_agent.process_payment_event(
        event=event,
        appointment=appointment,
        language=language,
        ghl_contact_id=ghl_contact_id,
    )

    # Persist payment record to Supabase
    if payment_record and appointment:
        payment_data = {
            "id": payment_record.id,
            "lead_id": payment_record.lead_id,
            "appointment_id": appointment.id,
            "stripe_payment_intent_id": payment_record.stripe_payment_intent_id,
            "stripe_session_id": payment_record.stripe_session_id,
            "amount": float(payment_record.amount),
            "currency": payment_record.currency,
            "status": payment_record.status.value,
            "paid_at": payment_record.paid_at.isoformat() if payment_record.paid_at else None,
        }
        supabase.table("payment_records").insert(payment_data).execute()

        # Update appointment status
        supabase.table("appointment_slots").update(
            {"status": "confirmed"}
        ).eq("id", appointment.id).execute()

    await session_manager.log_event(
        event_type="payment_confirmed",
        lead_id=lead_id,
        event_data={
            "stripe_event_type": event.get("type"),
            "appointment_id": appointment_id,
            "amount": payment_info.get("amount_cents", 0) / 100,
        },
    )

    logger.info(
        "payment_confirmation_handled",
        lead_id=lead_id,
        appointment_id=appointment_id,
    )

    return {
        "status": "ok",
        "lead_id": lead_id,
        "appointment_id": appointment_id,
        "payment_confirmed": True,
    }


@router.get("/success")
async def payment_success():
    """
    Redirect landing page after successful Stripe payment.
    Caller lands here after completing payment on mobile.
    """
    return {
        "status": "payment_complete",
        "message": (
            "Your consultation has been confirmed. "
            "You will receive an SMS confirmation shortly."
        ),
    }


@router.get("/cancelled")
async def payment_cancelled():
    """Landing page when a caller cancels the Stripe checkout."""
    return {
        "status": "payment_cancelled",
        "message": (
            "Your payment was not completed. "
            "Please call us back to reschedule your consultation."
        ),
    }