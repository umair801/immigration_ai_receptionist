import structlog
from typing import TypedDict, Optional, Annotated
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from core.config import get_settings
from core.enums import Language, UrgencyLevel, CaseType
from core.models import IntakeRecord

logger = structlog.get_logger()
settings = get_settings()

# ------------------------------------------------------------------
# Intake questions in English and Spanish
# ------------------------------------------------------------------

QUESTIONS = {
    Language.ENGLISH: {
        "greeting": (
            "Thank you for calling. My name is Sofia, and I am the intake "
            "specialist here. I will ask you a few quick questions to make "
            "sure we connect you with the right attorney. This will only "
            "take about two minutes. May I have your full name please?"
        ),
        "reason": (
            "Thank you {name}. Can you briefly tell me the reason for your "
            "call today? For example, are you looking for help with a visa, "
            "a green card, deportation defense, or something else?"
        ),
        "country": (
            "I understand. What country are you originally from?"
        ),
        "entry_date": (
            "And approximately when did you first enter the United States? "
            "Just the year is fine if you are not sure of the exact date."
        ),
        "family_status": (
            "Do you have any immediate family members who are US citizens "
            "or permanent residents, such as a spouse, parent, or child?"
        ),
        "court": (
            "Have you ever received any notices from an immigration court, "
            "or do you currently have a court hearing scheduled?"
        ),
        "detained": (
            "Are you or anyone in your family currently being held in "
            "immigration detention?"
        ),
        "closing": (
            "Thank you {name}, I have everything I need. One of our "
            "attorneys will review your information and we will be in touch "
            "shortly to schedule your consultation. Is there anything else "
            "you would like me to note before we finish?"
        ),
        "escalation": (
            "Given what you have described, I am going to connect you with "
            "one of our attorneys right now. Please hold for just a moment."
        ),
    },
    Language.SPANISH: {
        "greeting": (
            "Gracias por llamar. Mi nombre es Sofia y soy la especialista "
            "de admisiones. Le voy a hacer algunas preguntas rapidas para "
            "conectarle con el abogado correcto. Solo tomara unos dos "
            "minutos. Me puede dar su nombre completo por favor?"
        ),
        "reason": (
            "Gracias {name}. Me puede decir brevemente el motivo de su "
            "llamada hoy? Por ejemplo, necesita ayuda con una visa, "
            "una tarjeta verde, defensa contra deportacion, u otra cosa?"
        ),
        "country": (
            "Entiendo. De que pais es usted originalmente?"
        ),
        "entry_date": (
            "Y aproximadamente cuando entro usted por primera vez a los "
            "Estados Unidos? Solo el ano esta bien si no recuerda la "
            "fecha exacta."
        ),
        "family_status": (
            "Tiene algun familiar inmediato que sea ciudadano americano "
            "o residente permanente, como un conyuge, padre, o hijo?"
        ),
        "court": (
            "Ha recibido alguna vez notificaciones de un tribunal de "
            "inmigracion, o tiene actualmente una audiencia programada?"
        ),
        "detained": (
            "Usted o algun miembro de su familia esta actualmente detenido "
            "por inmigracion?"
        ),
        "closing": (
            "Gracias {name}, ya tengo todo lo que necesito. Uno de nuestros "
            "abogados revisara su informacion y nos comunicaremos con usted "
            "pronto para programar su consulta. Hay algo mas que quiera "
            "que anote antes de terminar?"
        ),
        "escalation": (
            "Dada la situacion que me ha descrito, voy a conectarle con "
            "uno de nuestros abogados ahora mismo. Por favor espere "
            "un momento."
        ),
    },
}

# ------------------------------------------------------------------
# LangGraph state definition
# ------------------------------------------------------------------

class IntakeState(TypedDict):
    call_session_id: str
    lead_id: str
    phone_number: str
    language: Language
    current_step: str
    name: Optional[str]
    reason_for_calling: Optional[str]
    country_of_origin: Optional[str]
    entry_date: Optional[str]
    family_status: Optional[str]
    court_involvement: bool
    is_detained: bool
    additional_notes: Optional[str]
    last_agent_message: str
    last_caller_message: str
    requires_escalation: bool
    intake_complete: bool
    intake_record: Optional[dict]


# ------------------------------------------------------------------
# GPT-4o extraction helper
# ------------------------------------------------------------------

llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.openai_api_key,
    temperature=0.0,
)


async def extract_field(
    caller_message: str,
    field: str,
    language: Language,
) -> str:
    """
    Use GPT-4o to extract a specific field from a free-form caller response.
    Returns a clean, normalized string value.
    """
    lang_label = "Spanish" if language == Language.SPANISH else "English"

    system_prompt = (
        f"You are extracting structured data from a caller's spoken response "
        f"during an immigration intake call. The caller is speaking {lang_label}. "
        f"Extract only the value for the field: '{field}'. "
        f"Return only the extracted value as a short clean string. "
        f"If the caller did not provide this information, return 'unknown'. "
        f"Never add explanation or extra words."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Caller said: {caller_message}"),
    ]

    response = await llm.ainvoke(messages)
    return response.content.strip()


async def detect_urgency(state: IntakeState) -> UrgencyLevel:
    """Determine urgency level from collected intake data."""
    if state.get("is_detained"):
        return UrgencyLevel.CRITICAL

    court_text = (state.get("court_involvement") or "")
    reason_text = (state.get("reason_for_calling") or "").lower()

    urgent_keywords = [
        "court", "hearing", "deport", "removal", "tribunal",
        "audiencia", "deportacion", "detenido", "detained"
    ]

    if any(kw in reason_text for kw in urgent_keywords):
        return UrgencyLevel.HIGH

    return UrgencyLevel.MEDIUM


async def detect_case_type(state: IntakeState) -> CaseType:
    """Map the caller's reason to a structured case type using GPT-4o."""
    reason = state.get("reason_for_calling", "")
    if not reason or reason == "unknown":
        return CaseType.UNKNOWN

    # Short-circuit for obvious keywords to avoid unnecessary API calls
    reason_lower = reason.lower()
    if state.get("is_detained") or "detention" in reason_lower or "detenido" in reason_lower:
        return CaseType.DETENTION
    if "asylum" in reason_lower or "asilo" in reason_lower:
        return CaseType.ASYLUM
    if "daca" in reason_lower:
        return CaseType.DACA
    if "naturalization" in reason_lower or "citizenship" in reason_lower:
        return CaseType.NATURALIZATION

    system_prompt = (
        "You are classifying an immigration case type. "
        "Based on the caller's stated reason, return exactly one of these "
        "case type labels: asylum, removal_defense, family_petition, "
        "naturalization, daca, visa_application, work_permit, green_card, "
        "detention, other. Return only the label, nothing else."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Caller reason: {reason}"),
    ]

    response = await llm.ainvoke(messages)
    label = response.content.strip().lower()

    try:
        return CaseType(label)
    except ValueError:
        return CaseType.OTHER


# ------------------------------------------------------------------
# LangGraph nodes
# ------------------------------------------------------------------

async def node_greeting(state: IntakeState) -> IntakeState:
    """Send the opening greeting and ask for the caller's name."""
    lang = state["language"]
    message = QUESTIONS[lang]["greeting"]
    logger.info("intake_node_greeting", language=lang)
    return {
        **state,
        "current_step": "collect_name",
        "last_agent_message": message,
    }


async def node_collect_name(state: IntakeState) -> IntakeState:
    """Extract the caller's name from their response."""
    name = await extract_field(
        state["last_caller_message"], "full name", state["language"]
    )
    lang = state["language"]
    message = QUESTIONS[lang]["reason"].format(name=name)
    logger.info("intake_node_collect_name", name=name)
    return {
        **state,
        "name": name,
        "current_step": "collect_reason",
        "last_agent_message": message,
    }


async def node_collect_reason(state: IntakeState) -> IntakeState:
    """Extract reason for calling and ask about country of origin."""
    reason = await extract_field(
        state["last_caller_message"], "reason for calling", state["language"]
    )
    lang = state["language"]
    message = QUESTIONS[lang]["country"]
    logger.info("intake_node_collect_reason", reason=reason)
    return {
        **state,
        "reason_for_calling": reason,
        "current_step": "collect_country",
        "last_agent_message": message,
    }


async def node_collect_country(state: IntakeState) -> IntakeState:
    """Extract country of origin and ask about entry date."""
    country = await extract_field(
        state["last_caller_message"], "country of origin", state["language"]
    )
    lang = state["language"]
    message = QUESTIONS[lang]["entry_date"]
    logger.info("intake_node_collect_country", country=country)
    return {
        **state,
        "country_of_origin": country,
        "current_step": "collect_entry_date",
        "last_agent_message": message,
    }


async def node_collect_entry_date(state: IntakeState) -> IntakeState:
    """Extract entry date and ask about family status."""
    entry_date = await extract_field(
        state["last_caller_message"], "entry date to the US", state["language"]
    )
    lang = state["language"]
    message = QUESTIONS[lang]["family_status"]
    logger.info("intake_node_collect_entry_date", entry_date=entry_date)
    return {
        **state,
        "entry_date": entry_date,
        "current_step": "collect_family_status",
        "last_agent_message": message,
    }


async def node_collect_family_status(state: IntakeState) -> IntakeState:
    """Extract family status and ask about court involvement."""
    family = await extract_field(
        state["last_caller_message"],
        "family members who are US citizens or permanent residents",
        state["language"],
    )
    lang = state["language"]
    message = QUESTIONS[lang]["court"]
    logger.info("intake_node_collect_family_status", family_status=family)
    return {
        **state,
        "family_status": family,
        "current_step": "collect_court",
        "last_agent_message": message,
    }


async def node_collect_court(state: IntakeState) -> IntakeState:
    """Extract court involvement and ask about detention."""
    court_raw = await extract_field(
        state["last_caller_message"],
        "court notices or scheduled hearings",
        state["language"],
    )
    has_court = any(
        kw in court_raw.lower()
        for kw in ["yes", "si", "have", "tengo", "scheduled", "programada"]
    )
    lang = state["language"]
    message = QUESTIONS[lang]["detained"]
    logger.info("intake_node_collect_court", court_involvement=has_court)
    return {
        **state,
        "court_involvement": has_court,
        "current_step": "collect_detained",
        "last_agent_message": message,
    }


async def node_collect_detained(state: IntakeState) -> IntakeState:
    """Extract detention status and decide next routing."""
    detained_raw = await extract_field(
        state["last_caller_message"],
        "currently detained by immigration",
        state["language"],
    )
    is_detained = any(
        kw in detained_raw.lower()
        for kw in ["yes", "si", "detained", "detenido", "held", "detenida"]
    )
    logger.info("intake_node_collect_detained", is_detained=is_detained)

    if is_detained:
        lang = state["language"]
        message = QUESTIONS[lang]["escalation"]
        return {
            **state,
            "is_detained": True,
            "requires_escalation": True,
            "current_step": "escalate",
            "last_agent_message": message,
        }

    return {
        **state,
        "is_detained": False,
        "current_step": "closing",
        "last_agent_message": "",
    }


async def node_closing(state: IntakeState) -> IntakeState:
    """Deliver closing message and finalize the intake record."""
    lang = state["language"]
    name = state.get("name", "")
    message = QUESTIONS[lang]["closing"].format(name=name)

    urgency = await detect_urgency(state)
    case_type = await detect_case_type(state)

    intake_record = IntakeRecord(
        lead_id=state["lead_id"],
        call_session_id=state["call_session_id"],
        name=state.get("name", ""),
        phone_number=state["phone_number"],
        country_of_origin=state.get("country_of_origin"),
        entry_date=state.get("entry_date"),
        family_status=state.get("family_status"),
        immigration_history=state.get("reason_for_calling"),
        court_involvement=state.get("court_involvement", False),
        is_detained=state.get("is_detained", False),
        urgency_level=urgency,
        case_type=case_type,
        language=lang,
        additional_notes=state.get("additional_notes"),
    )

    logger.info(
        "intake_complete",
        lead_id=state["lead_id"],
        urgency=urgency,
        case_type=case_type,
    )

    return {
        **state,
        "current_step": "complete",
        "last_agent_message": message,
        "intake_complete": True,
        "intake_record": intake_record.model_dump(),
    }


async def node_escalate(state: IntakeState) -> IntakeState:
    """Mark the call for immediate escalation to a live attorney."""
    urgency = await detect_urgency(state)
    case_type = await detect_case_type(state)

    intake_record = IntakeRecord(
        lead_id=state["lead_id"],
        call_session_id=state["call_session_id"],
        name=state.get("name", ""),
        phone_number=state["phone_number"],
        country_of_origin=state.get("country_of_origin"),
        entry_date=state.get("entry_date"),
        family_status=state.get("family_status"),
        immigration_history=state.get("reason_for_calling"),
        court_involvement=state.get("court_involvement", False),
        is_detained=True,
        urgency_level=urgency,
        case_type=case_type,
        language=state["language"],
    )

    logger.info(
        "intake_escalated",
        lead_id=state["lead_id"],
        reason="detention_detected",
    )

    return {
        **state,
        "current_step": "complete",
        "intake_complete": True,
        "requires_escalation": True,
        "intake_record": intake_record.model_dump(),
    }


# ------------------------------------------------------------------
# Routing logic
# ------------------------------------------------------------------

def route_after_detained(state: IntakeState) -> str:
    if state.get("requires_escalation"):
        return "escalate"
    return "closing"


# ------------------------------------------------------------------
# Build the LangGraph
# ------------------------------------------------------------------

def build_intake_graph() -> StateGraph:
    graph = StateGraph(IntakeState)

    graph.add_node("greeting", node_greeting)
    graph.add_node("collect_name", node_collect_name)
    graph.add_node("collect_reason", node_collect_reason)
    graph.add_node("collect_country", node_collect_country)
    graph.add_node("collect_entry_date", node_collect_entry_date)
    graph.add_node("collect_family_status", node_collect_family_status)
    graph.add_node("collect_court", node_collect_court)
    graph.add_node("collect_detained", node_collect_detained)
    graph.add_node("closing", node_closing)
    graph.add_node("escalate", node_escalate)

    graph.set_entry_point("greeting")

    graph.add_edge("greeting", "collect_name")
    graph.add_edge("collect_name", "collect_reason")
    graph.add_edge("collect_reason", "collect_country")
    graph.add_edge("collect_country", "collect_entry_date")
    graph.add_edge("collect_entry_date", "collect_family_status")
    graph.add_edge("collect_family_status", "collect_court")
    graph.add_edge("collect_court", "collect_detained")

    graph.add_conditional_edges(
        "collect_detained",
        route_after_detained,
        {"escalate": "escalate", "closing": "closing"},
    )

    graph.add_edge("closing", END)
    graph.add_edge("escalate", END)

    return graph.compile()


# Compiled graph instance
intake_graph = build_intake_graph()