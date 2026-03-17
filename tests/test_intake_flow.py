import asyncio
import unittest
from core.enums import Language, CaseType
from agents.intake_agent import (
    build_intake_graph,
    node_greeting,
    node_collect_name,
    node_collect_reason,
    node_collect_country,
    node_collect_entry_date,
    node_collect_family_status,
    node_collect_court,
    node_collect_detained,
    node_closing,
    node_escalate,
    IntakeState,
)


def make_state(language: Language = Language.ENGLISH) -> IntakeState:
    return IntakeState(
        call_session_id="test-session-001",
        lead_id="test-lead-001",
        phone_number="+13051234567",
        language=language,
        current_step="greeting",
        name=None,
        reason_for_calling=None,
        country_of_origin=None,
        entry_date=None,
        family_status=None,
        court_involvement=False,
        is_detained=False,
        additional_notes=None,
        last_agent_message="",
        last_caller_message="",
        requires_escalation=False,
        intake_complete=False,
        intake_record=None,
    )


class TestIntakeFlow(unittest.TestCase):

    def test_1_graph_compiles(self):
        graph = build_intake_graph()
        self.assertIsNotNone(graph)

    def test_2_greeting_english(self):
        async def run():
            state = make_state(Language.ENGLISH)
            result = await node_greeting(state)
            self.assertIn("Sofia", result["last_agent_message"])
            self.assertEqual(result["current_step"], "collect_name")
        asyncio.run(run())

    def test_3_greeting_spanish(self):
        async def run():
            state = make_state(Language.SPANISH)
            result = await node_greeting(state)
            self.assertIn("Sofia", result["last_agent_message"])
            self.assertIn("nombre", result["last_agent_message"].lower())
        asyncio.run(run())

    def test_4_full_english_intake(self):
        """Full GPT-4o intake flow. Must run before any other async GPT-4o test."""
        async def run():
            state = make_state(Language.ENGLISH)
            state = await node_greeting(state)
            state["last_caller_message"] = "My name is James Carter"
            state = await node_collect_name(state)
            self.assertIsNotNone(state["name"])

            state["last_caller_message"] = "I need help with a green card"
            state = await node_collect_reason(state)
            self.assertIsNotNone(state["reason_for_calling"])

            state["last_caller_message"] = "I am from Jamaica"
            state = await node_collect_country(state)
            self.assertIsNotNone(state["country_of_origin"])

            state["last_caller_message"] = "I came in 2015"
            state = await node_collect_entry_date(state)
            self.assertIsNotNone(state["entry_date"])

            state["last_caller_message"] = "My wife is a US citizen"
            state = await node_collect_family_status(state)
            self.assertIsNotNone(state["family_status"])

            state["last_caller_message"] = "No court hearings"
            state = await node_collect_court(state)

            state["last_caller_message"] = "No I am not detained"
            state = await node_collect_detained(state)
            self.assertFalse(state["is_detained"])
            self.assertFalse(state["requires_escalation"])

            state = await node_closing(state)
            self.assertTrue(state["intake_complete"])
            self.assertIsNotNone(state["intake_record"])
        asyncio.run(run())

    def test_5_detained_triggers_escalation(self):
        """Tests escalation routing logic without any API call."""
        from agents.intake_agent import route_after_detained

        # Simulate state where detained=True
        state = make_state(Language.SPANISH)
        state["name"] = "Maria"
        state["is_detained"] = True
        state["requires_escalation"] = True

        route = route_after_detained(state)
        self.assertEqual(route, "escalate")

        # Simulate state where detained=False
        state2 = make_state(Language.SPANISH)
        state2["is_detained"] = False
        state2["requires_escalation"] = False

        route2 = route_after_detained(state2)
        self.assertEqual(route2, "closing")

    def test_6_escalate_node_completes_intake(self):
        """No GPT-4o call. Uses keyword shortcut in detect_case_type."""
        async def run():
            state = make_state(Language.SPANISH)
            state["name"] = "Maria Gonzalez"
            state["reason_for_calling"] = "detention"
            state["country_of_origin"] = "Honduras"
            state["is_detained"] = True
            state["requires_escalation"] = True
            state = await node_escalate(state)
            self.assertTrue(state["intake_complete"])
            self.assertIsNotNone(state["intake_record"])
            self.assertEqual(state["intake_record"]["urgency_level"], "critical")
            self.assertEqual(
                state["intake_record"]["case_type"],
                CaseType.DETENTION.value,
            )
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()