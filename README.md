# AI Immigration Receptionist

**Autonomous bilingual AI receptionist system for immigration law firms.**

Handles inbound and outbound calls in English and Spanish, qualifies leads through structured intake conversations, books consultations with payment confirmation, transfers calls to paralegals when needed, and logs every interaction into GoHighLevel — with no human receptionist involvement.

Built by [Datawebify](https://datawebify.com) | [GitHub](https://github.com/umair801) | [Upwork](https://upwork.com/freelancers/umair801)

---

## Business Outcomes

| Metric | Manual Receptionist | With This System | Change |
|---|---|---|---|
| Call answer rate | 60-70% (missed after hours) | 100% (24/7) | Full coverage |
| Time to first intake question | 2-5 minutes | Under 10 seconds | 97% faster |
| Intake completion rate | 50-60% | 85%+ | +30 points |
| Consultation booking rate | 20-30% of calls | 40-55% of calls | 2x improvement |
| Staff time on intake calls | 15-20 hrs/week | Near zero | 90% reduction |
| Lead data in CRM | Inconsistent, manual | 100% automated | Full coverage |

---

## What It Does

**Inbound calls** are answered instantly by a bilingual AI agent named Sofia. Sofia detects the caller's language, conducts a structured immigration intake conversation, qualifies the lead, books a consultation, sends a Stripe payment link via SMS, and logs the complete interaction into GoHighLevel — all before any staff member is involved.

**Outbound calls** are triggered automatically when a new lead enters GoHighLevel from a Facebook or Instagram form submission. Sofia calls the lead within seconds of form submission, in their preferred language, and runs the same intake and qualification flow as inbound calls.

**Urgent cases** involving detention or imminent court hearings are flagged immediately and transferred to a live attorney with a whispered caller summary delivered before the connection is made.

**Every call** produces a structured CRM record with intake fields, qualification score, attorney brief, appointment details, payment status, call transcript, and pipeline stage update.

---

## System Architecture

```
Inbound Call / Social Media Lead
           |
     Twilio (routing)
           |
      Retell AI (voice agent)
           |
     ElevenLabs (bilingual TTS)
           |
   New Lead          Existing Client
      |                    |
 Intake Agent        Transfer to Paralegal
      |
 Qualification Agent (GPT-4o)
      |
 Appointment Setter Agent
      |
 Payment Confirmation Agent
      |
 CRM Sync Agent (GoHighLevel)
      |
 SMS + Calendar Confirmation
```

### Agent Pipeline

**Call Router Agent** — Receives inbound calls via Twilio webhook, detects caller type via GoHighLevel lookup, routes new leads to intake and existing clients to warm transfer.

**Intake Agent** — LangGraph conversation flow collecting name, country of origin, entry date, family status, immigration history, court involvement, and urgency level in English or Spanish.

**Qualification Agent** — GPT-4o lead scoring (0-100) evaluating case complexity, urgency, and firm fit. Detained callers and imminent court hearings trigger immediate escalation.

**Appointment Setter Agent** — Fetches live Google Calendar availability, presents three options to the caller, confirms selection, generates a Stripe payment link, and delivers it via Twilio SMS.

**Payment Confirmation Agent** — Listens for Stripe webhook on payment completion, finalizes the appointment, sends confirmation and 24-hour reminder SMS, and updates GoHighLevel.

**Outbound Caller Agent** — Triggered by GoHighLevel pipeline stage changes or lead form submissions. Runs the full intake and qualification flow on outbound calls.

**Call Transfer Agent** — Executes warm transfers to paralegals or attorneys using Twilio conference logic. Whispers a caller summary to the receiving staff member before connection.

**CRM Sync Agent** — Writes the complete call record to GoHighLevel after every call: intake fields, qualification score, attorney brief, appointment details, payment status, transcript, and pipeline stage.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph |
| AI Model | GPT-4o (OpenAI API) |
| Voice Platform | Retell AI |
| Telephony | Twilio Voice |
| Voice Synthesis | ElevenLabs (bilingual) |
| CRM | GoHighLevel |
| Calendar | Google Calendar API |
| Payment | Stripe |
| Backend API | FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Deployment | Docker + Railway |
| Language | Python 3.12 |

---

## Project Structure

```
AgAI_9_Immigration_AI_Receptionist/
├── agents/
│   ├── call_router_agent.py
│   ├── intake_agent.py
│   ├── qualification_agent.py
│   ├── appointment_setter_agent.py
│   ├── payment_confirmation_agent.py
│   ├── outbound_caller_agent.py
│   ├── call_transfer_agent.py
│   └── crm_sync_agent.py
├── core/
│   ├── orchestrator.py
│   ├── config.py
│   ├── database.py
│   ├── session_manager.py
│   ├── models.py
│   ├── enums.py
│   └── logger.py
├── api/
│   ├── main.py
│   ├── voice_router.py
│   ├── payment_router.py
│   └── metrics_router.py
├── integrations/
│   ├── retell_client.py
│   ├── elevenlabs_client.py
│   ├── ghl_client.py
│   ├── stripe_client.py
│   └── google_calendar_client.py
├── notifications/
│   └── sms_sender.py
├── tests/
│   ├── test_intake_flow.py
│   ├── test_qualification.py
│   ├── test_call_transfer.py
│   ├── test_payment_confirmation.py
│   └── test_crm_sync.py
├── Dockerfile
├── railway.json
├── requirements.txt
├── schema.sql
├── .env.example
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/voice/retell-webhook` | Retell AI call event receiver |
| POST | `/voice/intake-webhook` | Demo intake data receiver |
| POST | `/voice/trigger-outbound` | GoHighLevel outbound call trigger |
| POST | `/payment/stripe-webhook` | Stripe payment confirmation |
| GET | `/payment/success` | Post-payment redirect |
| GET | `/metrics/` | Live KPI dashboard |
| GET | `/metrics/summary` | Executive summary report |
| GET | `/metrics/health` | Health and database status |
| GET | `/health` | Server health check |
| GET | `/docs` | Interactive API documentation |

---

## Metrics Tracked

- Calls received (total, by language)
- Intake completion rate vs 85% target
- Consultation booking rate vs 45% target
- Revenue captured (USD)
- Hot, warm, and cold lead counts
- Urgent escalations triggered
- Human receptionist hours: zero

Live metrics available at `/metrics/` on the deployed instance.

---

## Local Setup

```bash
# Clone the repository
git clone https://github.com/umair801/immigration_ai_receptionist.git
cd agai9-immigration-ai-receptionist

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in all API keys in .env

# Apply database schema
# Run schema.sql in your Supabase SQL Editor

# Start the server
python main.py
```

Server runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

---

## Environment Variables

```env
OPENAI_API_KEY=
RETELL_API_KEY=
RETELL_AGENT_ID=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID_EN=
ELEVENLABS_VOICE_ID_ES=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
GHL_API_KEY=
GHL_LOCATION_ID=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
APP_ENV=production
APP_PORT=8000
BASE_URL=https://immigration.datawebify.com/
```

---

## Deployment

The system deploys to Railway via Docker. After pushing to GitHub:

1. Connect the repository to Railway
2. Add all environment variables in Railway dashboard
3. Railway auto-detects the Dockerfile and deploys
4. Health check confirms live status at `/health`
5. Update `BASE_URL` in environment variables with the Railway domain
6. Register the Railway webhook URL in Retell AI dashboard
7. Register the Stripe webhook endpoint in Stripe dashboard

---

## Running Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

35 tests across intake flow, qualification scoring, call transfer routing, payment confirmation, and CRM sync logic.

---

## Intake Fields Collected

- Full name
- Country of origin
- US entry date
- Family member citizenship status
- Immigration history and reason for calling
- Court hearing involvement
- Detention status
- Preferred language (English or Spanish)

---

## Lead Qualification Scoring

Leads are scored 0-100 based on urgency level, case type, family status, court involvement, and completeness of intake data.

| Score | Label | Action |
|---|---|---|
| 75-100 | Hot | Priority follow-up, immediate booking |
| 50-74 | Warm | Standard consultation booking |
| 25-49 | Cold | Nurture sequence triggered in GHL |
| 0-24 | Unqualified | Tagged and archived |

Detained callers and callers with imminent court hearings bypass scoring and escalate directly to a live attorney regardless of score.

---

## Call Transfer Logic

| Condition | Transfer Target |
|---|---|
| Detained or critical urgency | Senior Attorney |
| Spanish-speaking standard lead | Spanish Paralegal |
| English-speaking standard lead | Default Paralegal Team |

All transfers include a whispered caller summary delivered to the receiving staff member before the caller is connected.

---

## Built By

**Muhammad Umair** — Agentic AI Specialist and Enterprise Consultant

[Datawebify](https://datawebify.com) | [GitHub](https://github.com/umair801) | [Upwork](https://upwork.com/freelancers/umair801)

This system is Project 9 in a portfolio of 50 enterprise-grade agentic AI systems built for professional services firms.
