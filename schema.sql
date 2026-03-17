-- ============================================================
-- AgAI-9 Immigration AI Receptionist
-- Supabase Schema
-- ============================================================

-- Enable UUID generation
create extension if not exists "pgcrypto";


-- ============================================================
-- leads
-- ============================================================
create table if not exists leads (
    id uuid primary key default gen_random_uuid(),
    phone_number text not null,
    name text,
    email text,
    language text not null default 'en',
    caller_type text not null default 'unknown',
    ghl_contact_id text,
    created_at timestamptz not null default now()
);

create index if not exists leads_phone_idx on leads (phone_number);
create index if not exists leads_ghl_idx on leads (ghl_contact_id);


-- ============================================================
-- call_sessions
-- ============================================================
create table if not exists call_sessions (
    id uuid primary key default gen_random_uuid(),
    call_id text not null unique,
    phone_number text not null,
    lead_id uuid references leads (id),
    caller_type text not null default 'unknown',
    language text not null default 'en',
    status text not null default 'initiated',
    intake_id uuid,
    qualification_id uuid,
    appointment_id uuid,
    payment_id uuid,
    transcript text,
    call_summary text,
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    duration_seconds integer
);

create index if not exists call_sessions_call_id_idx on call_sessions (call_id);
create index if not exists call_sessions_lead_id_idx on call_sessions (lead_id);
create index if not exists call_sessions_status_idx on call_sessions (status);
create index if not exists call_sessions_started_at_idx on call_sessions (started_at);


-- ============================================================
-- intake_records
-- ============================================================
create table if not exists intake_records (
    id uuid primary key default gen_random_uuid(),
    lead_id uuid not null references leads (id),
    call_session_id uuid not null references call_sessions (id),
    name text not null,
    phone_number text not null,
    country_of_origin text,
    entry_date text,
    family_status text,
    immigration_history text,
    court_involvement boolean not null default false,
    is_detained boolean not null default false,
    urgency_level text not null default 'low',
    case_type text not null default 'unknown',
    language text not null default 'en',
    additional_notes text,
    created_at timestamptz not null default now()
);

create index if not exists intake_records_lead_id_idx on intake_records (lead_id);
create index if not exists intake_records_session_idx on intake_records (call_session_id);
create index if not exists intake_records_urgency_idx on intake_records (urgency_level);
create index if not exists intake_records_detained_idx on intake_records (is_detained);


-- ============================================================
-- qualification_results
-- ============================================================
create table if not exists qualification_results (
    id uuid primary key default gen_random_uuid(),
    lead_id uuid not null references leads (id),
    intake_id uuid not null references intake_records (id),
    score integer not null check (score >= 0 and score <= 100),
    label text not null,
    case_type text not null,
    urgency_level text not null,
    requires_escalation boolean not null default false,
    escalation_reason text,
    summary text not null,
    scored_at timestamptz not null default now()
);

create index if not exists qual_results_lead_id_idx on qualification_results (lead_id);
create index if not exists qual_results_score_idx on qualification_results (score);
create index if not exists qual_results_escalation_idx on qualification_results (requires_escalation);


-- ============================================================
-- appointment_slots
-- ============================================================
create table if not exists appointment_slots (
    id uuid primary key default gen_random_uuid(),
    lead_id uuid not null references leads (id),
    start_time timestamptz not null,
    end_time timestamptz not null,
    attorney_name text,
    ghl_calendar_id text,
    google_event_id text,
    status text not null default 'pending_payment',
    stripe_payment_link text,
    created_at timestamptz not null default now()
);

create index if not exists appointments_lead_id_idx on appointment_slots (lead_id);
create index if not exists appointments_status_idx on appointment_slots (status);
create index if not exists appointments_start_time_idx on appointment_slots (start_time);


-- ============================================================
-- payment_records
-- ============================================================
create table if not exists payment_records (
    id uuid primary key default gen_random_uuid(),
    lead_id uuid not null references leads (id),
    appointment_id uuid not null references appointment_slots (id),
    stripe_payment_intent_id text,
    stripe_session_id text,
    amount numeric(10, 2) not null,
    currency text not null default 'usd',
    status text not null default 'pending',
    paid_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists payments_lead_id_idx on payment_records (lead_id);
create index if not exists payments_status_idx on payment_records (status);
create index if not exists payments_stripe_idx on payment_records (stripe_payment_intent_id);


-- ============================================================
-- call_logs (append-only event log)
-- ============================================================
create table if not exists call_logs (
    id uuid primary key default gen_random_uuid(),
    call_session_id uuid references call_sessions (id),
    lead_id uuid references leads (id),
    event_type text not null,
    event_data jsonb,
    created_at timestamptz not null default now()
);

create index if not exists call_logs_session_idx on call_logs (call_session_id);
create index if not exists call_logs_event_type_idx on call_logs (event_type);
create index if not exists call_logs_created_at_idx on call_logs (created_at);


-- ============================================================
-- metrics_snapshots (for /metrics endpoint)
-- ============================================================
create table if not exists metrics_snapshots (
    id uuid primary key default gen_random_uuid(),
    snapshot_date date not null default current_date,
    calls_received integer not null default 0,
    intake_completions integer not null default 0,
    consultations_booked integer not null default 0,
    payments_confirmed integer not null default 0,
    escalations integer not null default 0,
    revenue_captured numeric(10, 2) not null default 0,
    created_at timestamptz not null default now()
);

create unique index if not exists metrics_date_idx on metrics_snapshots (snapshot_date);