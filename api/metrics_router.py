import structlog
from fastapi import APIRouter, Query
from datetime import datetime, date, timedelta
from typing import Optional

from core.database import supabase

logger = structlog.get_logger()
router = APIRouter(prefix="/metrics", tags=["metrics"])


def safe_count(table: str, filters: Optional[list] = None) -> int:
    """Run a count query on a Supabase table with optional filters."""
    try:
        query = supabase.table(table).select("id", count="exact")
        if filters:
            for col, op, val in filters:
                if op == "eq":
                    query = query.eq(col, val)
                elif op == "gte":
                    query = query.gte(col, val)
                elif op == "lte":
                    query = query.lte(col, val)
        result = query.execute()
        return result.count or 0
    except Exception as e:
        logger.error("metrics_count_error", table=table, error=str(e))
        return 0


def safe_sum(table: str, column: str, filters: Optional[list] = None) -> float:
    """Sum a numeric column in a Supabase table with optional filters."""
    try:
        query = supabase.table(table).select(column)
        if filters:
            for col, op, val in filters:
                if op == "eq":
                    query = query.eq(col, val)
                elif op == "gte":
                    query = query.gte(col, val)
        result = query.execute()
        if result.data:
            return sum(
                float(row.get(column, 0) or 0)
                for row in result.data
            )
        return 0.0
    except Exception as e:
        logger.error("metrics_sum_error", table=table, column=column, error=str(e))
        return 0.0


@router.get("/")
async def get_metrics(
    period: str = Query(
        default="today",
        description="Time period: today, week, month, all",
    )
):
    """
    Returns live KPIs from Supabase.
    Used for the demo dashboard and client reporting.

    Metrics returned:
    - calls_received
    - intake_completions
    - intake_completion_rate
    - consultations_booked
    - booking_rate
    - payments_confirmed
    - revenue_captured
    - escalations
    - spanish_callers
    - english_callers
    - period
    - generated_at
    """
    now = datetime.utcnow()

    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        since = None

    since_str = since.isoformat() if since else None
    date_filter = [("started_at", "gte", since_str)] if since_str else None
    created_filter = [("created_at", "gte", since_str)] if since_str else None

    # Core call metrics
    calls_received = safe_count("call_sessions", date_filter)

    intake_completions = safe_count(
        "intake_records",
        created_filter,
    )

    intake_completion_rate = (
        round((intake_completions / calls_received) * 100, 1)
        if calls_received > 0
        else 0.0
    )

    consultations_booked = safe_count(
        "appointment_slots",
        [("created_at", "gte", since_str)] if since_str else None,
    )

    booking_rate = (
        round((consultations_booked / calls_received) * 100, 1)
        if calls_received > 0
        else 0.0
    )

    payments_confirmed = safe_count(
        "payment_records",
        ([("created_at", "gte", since_str)] if since_str else None),
    )

    revenue_captured = safe_sum(
        "payment_records",
        "amount",
        ([("created_at", "gte", since_str)] if since_str else None),
    )

    escalations = safe_count(
        "call_logs",
        (
            [
                ("event_type", "eq", "call_started"),
                ("created_at", "gte", since_str),
            ]
            if since_str
            else [("event_type", "eq", "escalation_triggered")]
        ),
    )

    # Language breakdown
    try:
        spanish_query = supabase.table("call_sessions").select(
            "id", count="exact"
        ).eq("language", "es")
        if since_str:
            spanish_query = spanish_query.gte("started_at", since_str)
        spanish_result = spanish_query.execute()
        spanish_callers = spanish_result.count or 0
    except Exception:
        spanish_callers = 0

    english_callers = max(0, calls_received - spanish_callers)

    # Qualification breakdown
    try:
        hot_query = supabase.table("qualification_results").select(
            "id", count="exact"
        ).eq("label", "hot")
        if since_str:
            hot_query = hot_query.gte("scored_at", since_str)
        hot_result = hot_query.execute()
        hot_leads = hot_result.count or 0
    except Exception:
        hot_leads = 0

    try:
        warm_query = supabase.table("qualification_results").select(
            "id", count="exact"
        ).eq("label", "warm")
        if since_str:
            warm_query = warm_query.gte("scored_at", since_str)
        warm_result = warm_query.execute()
        warm_leads = warm_result.count or 0
    except Exception:
        warm_leads = 0

    logger.info(
        "metrics_fetched",
        period=period,
        calls=calls_received,
        intake_completions=intake_completions,
        revenue=revenue_captured,
    )

    return {
        "period": period,
        "generated_at": now.isoformat(),
        "calls": {
            "received": calls_received,
            "spanish": spanish_callers,
            "english": english_callers,
        },
        "intake": {
            "completions": intake_completions,
            "completion_rate_pct": intake_completion_rate,
        },
        "qualification": {
            "hot_leads": hot_leads,
            "warm_leads": warm_leads,
        },
        "appointments": {
            "booked": consultations_booked,
            "booking_rate_pct": booking_rate,
        },
        "payments": {
            "confirmed": payments_confirmed,
            "revenue_captured_usd": round(revenue_captured, 2),
        },
        "escalations": escalations,
        "benchmarks": {
            "target_intake_completion_pct": 85,
            "target_booking_rate_pct": 45,
            "manual_receptionist_intake_pct": 55,
            "manual_receptionist_booking_pct": 25,
        },
    }


@router.get("/summary")
async def get_summary():
    """
    Returns a plain-text executive summary of all-time metrics.
    Suitable for copy-pasting into a client report or proposal.
    """
    all_time = await get_metrics(period="all")

    calls = all_time["calls"]["received"]
    intake_rate = all_time["intake"]["completion_rate_pct"]
    booked = all_time["appointments"]["booked"]
    revenue = all_time["payments"]["revenue_captured_usd"]
    escalations = all_time["escalations"]
    spanish = all_time["calls"]["spanish"]

    summary = (
        f"AI Receptionist Performance Summary\n"
        f"{'=' * 45}\n"
        f"Total calls handled:        {calls}\n"
        f"Spanish-language callers:   {spanish}\n"
        f"Intake completion rate:     {intake_rate}%\n"
        f"Consultations booked:       {booked}\n"
        f"Revenue captured:           ${revenue:,.2f}\n"
        f"Urgent escalations:         {escalations}\n"
        f"Human receptionist hours:   0\n"
        f"{'=' * 45}\n"
        f"System status:              LIVE\n"
        f"Generated:                  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )

    return {"summary": summary, "data": all_time}


@router.get("/health")
async def health_check():
    """
    Simple health check endpoint.
    Returns database connectivity status.
    """
    try:
        supabase.table("call_sessions").select("id").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"

    return {
        "status": "ok",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "AI Immigration Receptionist",
        "version": "1.0.0",
    }