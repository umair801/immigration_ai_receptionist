import stripe
import structlog
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.models import AppointmentSlot, IntakeRecord

logger = structlog.get_logger()
settings = get_settings()

stripe.api_key = settings.stripe_secret_key

CONSULTATION_FEE_CENTS = 15000  # $150.00
CURRENCY = "usd"


class StripeClient:
    def __init__(self) -> None:
        self.secret_key: str = settings.stripe_secret_key
        self.webhook_secret: str = settings.stripe_webhook_secret

    # ------------------------------------------------------------------
    # Payment link creation
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def create_payment_link(
        self,
        intake: IntakeRecord,
        appointment: AppointmentSlot,
        amount_cents: int = CONSULTATION_FEE_CENTS,
        success_url: Optional[str] = None,
    ) -> str:
        """
        Create a Stripe payment link for a consultation fee.
        Embeds appointment and lead IDs in metadata so the webhook
        can match the payment back to the correct booking.
        Returns the payment link URL as a string.
        """
        base_url = settings.base_url
        success_redirect = success_url or f"{base_url}/payment/success"

        try:
            # Create a price object for this transaction
            price = stripe.Price.create(
                unit_amount=amount_cents,
                currency=CURRENCY,
                product_data={
                    "name": "Immigration Consultation",
                    "description": (
                        f"Consultation for {intake.name} "
                        f"on {appointment.start_time.strftime('%B %d at %I:%M %p')}"
                    ),
                },
            )

            # Create the payment link with metadata
            payment_link = stripe.PaymentLink.create(
                line_items=[{"price": price.id, "quantity": 1}],
                metadata={
                    "lead_id": intake.lead_id,
                    "appointment_id": appointment.id,
                    "call_session_id": intake.call_session_id,
                    "contact_name": intake.name,
                    "contact_phone": intake.phone_number,
                },
                after_completion={
                    "type": "redirect",
                    "redirect": {"url": success_redirect},
                },
            )

            logger.info(
                "stripe_payment_link_created",
                lead_id=intake.lead_id,
                appointment_id=appointment.id,
                amount_cents=amount_cents,
                payment_link_id=payment_link.id,
            )

            return payment_link.url

        except stripe.StripeError as e:
            logger.error(
                "stripe_payment_link_error",
                lead_id=intake.lead_id,
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Checkout session (alternative to payment link)
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def create_checkout_session(
        self,
        intake: IntakeRecord,
        appointment: AppointmentSlot,
        amount_cents: int = CONSULTATION_FEE_CENTS,
    ) -> dict:
        """
        Create a Stripe Checkout Session.
        Returns the session object including the session URL and ID.
        """
        base_url = settings.base_url

        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": CURRENCY,
                            "unit_amount": amount_cents,
                            "product_data": {
                                "name": "Immigration Consultation",
                                "description": (
                                    f"30-minute consultation for {intake.name}"
                                ),
                            },
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=f"{base_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base_url}/payment/cancelled",
                metadata={
                    "lead_id": intake.lead_id,
                    "appointment_id": appointment.id,
                    "call_session_id": intake.call_session_id,
                    "contact_name": intake.name,
                    "contact_phone": intake.phone_number,
                },
                expires_at=int(
                    appointment.start_time.timestamp() - 3600
                ),
            )

            logger.info(
                "stripe_checkout_session_created",
                lead_id=intake.lead_id,
                session_id=session.id,
                amount_cents=amount_cents,
            )

            return {
                "session_id": session.id,
                "url": session.url,
                "expires_at": session.expires_at,
            }

        except stripe.StripeError as e:
            logger.error(
                "stripe_checkout_session_error",
                lead_id=intake.lead_id,
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Webhook verification
    # ------------------------------------------------------------------

    def verify_webhook(
        self,
        raw_body: bytes,
        signature_header: str,
    ) -> dict:
        """
        Verify and parse an incoming Stripe webhook event.
        Raises ValueError if signature is invalid.
        Returns the parsed event dict on success.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload=raw_body,
                sig_header=signature_header,
                secret=self.webhook_secret,
            )
            logger.info(
                "stripe_webhook_verified",
                event_type=event["type"],
                event_id=event["id"],
            )
            return event

        except stripe.SignatureVerificationError as e:
            logger.error(
                "stripe_webhook_signature_invalid",
                error=str(e),
            )
            raise ValueError(f"Invalid Stripe webhook signature: {e}")

        except Exception as e:
            logger.error(
                "stripe_webhook_parse_error",
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Payment intent lookup
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def get_payment_intent(self, payment_intent_id: str) -> dict:
        """Retrieve a payment intent by ID to verify its status."""
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            logger.info(
                "stripe_payment_intent_retrieved",
                payment_intent_id=payment_intent_id,
                status=intent.status,
            )
            return dict(intent)
        except stripe.StripeError as e:
            logger.error(
                "stripe_payment_intent_error",
                payment_intent_id=payment_intent_id,
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Refund
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def create_refund(
        self,
        payment_intent_id: str,
        amount_cents: Optional[int] = None,
        reason: str = "requested_by_customer",
    ) -> dict:
        """Issue a full or partial refund for a completed payment."""
        try:
            refund_params: dict = {
                "payment_intent": payment_intent_id,
                "reason": reason,
            }
            if amount_cents:
                refund_params["amount"] = amount_cents

            refund = stripe.Refund.create(**refund_params)

            logger.info(
                "stripe_refund_created",
                payment_intent_id=payment_intent_id,
                refund_id=refund.id,
                amount_cents=amount_cents,
            )
            return dict(refund)

        except stripe.StripeError as e:
            logger.error(
                "stripe_refund_error",
                payment_intent_id=payment_intent_id,
                error=str(e),
            )
            raise


# Singleton instance
stripe_client = StripeClient()