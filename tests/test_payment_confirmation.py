import asyncio
import unittest
from datetime import datetime
from core.enums import AppointmentStatus, PaymentStatus
from core.models import AppointmentSlot
from agents.payment_confirmation_agent import PaymentConfirmationAgent


class TestPaymentConfirmation(unittest.TestCase):

    def setUp(self):
        self.agent = PaymentConfirmationAgent()
        self.appointment = AppointmentSlot(
            lead_id="lead-001",
            start_time=datetime(2026, 3, 18, 9, 0),
            end_time=datetime(2026, 3, 18, 9, 30),
            status=AppointmentStatus.PENDING_PAYMENT,
        )

    def _mock_event(self, event_type: str) -> dict:
        return {
            "type": event_type,
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount_received": 15000,
                    "currency": "usd",
                    "metadata": {
                        "lead_id": "lead-001",
                        "appointment_id": self.appointment.id,
                        "call_session_id": "session-001",
                        "contact_name": "Carlos Mendoza",
                        "contact_phone": "+13051234567",
                    },
                }
            },
        }

    def test_parse_payment_intent_succeeded(self):
        event = self._mock_event("payment_intent.succeeded")
        info = self.agent.parse_stripe_event(event)
        self.assertIsNotNone(info)
        self.assertEqual(info["lead_id"], "lead-001")
        self.assertEqual(info["amount_cents"], 15000)

    def test_parse_non_payment_event_returns_none(self):
        event = {"type": "customer.created", "data": {"object": {}}}
        result = self.agent.parse_stripe_event(event)
        self.assertIsNone(result)

    def test_build_payment_record_status_completed(self):
        event = self._mock_event("payment_intent.succeeded")
        info = self.agent.parse_stripe_event(event)
        record = self.agent.build_payment_record(info, self.appointment)
        self.assertEqual(record.status, PaymentStatus.COMPLETED)
        self.assertEqual(record.amount, 150.0)

    def test_finalize_appointment_sets_confirmed(self):
        finalized = self.agent.finalize_appointment(self.appointment)
        self.assertEqual(finalized.status, AppointmentStatus.CONFIRMED)

    def test_confirmation_sms_english(self):
        sms = self.agent.build_confirmation_sms("+13051234567", "March 18 at 9AM", "en")
        self.assertIn("confirmed", sms.lower())

    def test_confirmation_sms_spanish(self):
        sms = self.agent.build_confirmation_sms("+13051234567", "18 de marzo", "es")
        self.assertIn("confirmada", sms.lower())

    def test_reminder_sms_contains_time(self):
        reminder = self.agent.build_reminder_sms(self.appointment, "en")
        self.assertIn("09:00 AM", reminder)


if __name__ == "__main__":
    unittest.main()