# Iclinic Main Service

## Overview
The `main-service` acts as the primary business logic core of the Iclinic backend. It coordinates scheduling, appointment management, twilio verification, and houses the LangGraph AI voice assistance agent.

## Architecture
- **API Layer**: REST endpoints mapped to specific domain verticals like `/appointments` and `/voice`.
- **Agentic Flow Layer**: Complex state machines run using LangGraph to parse conversational AI outputs into transactional booking flows.
- **Service Layer**: Traditional domain managers handling scheduling constraints.
- **Data Layer**: Asynchronous PostgreSQL connections relying on `sqlalchemy.orm.Mapped` paradigms.

## Tech Stack
- **Framework**: FastAPI (Python 3.12)
- **AI/LLM**: LangChain, LangGraph, Sentence Transformers.
- **Voice/Comms**: Twilio, Deepgram SDK, Edge TTS.
- **Observability**: Prometheus, OpenTelemetry.

## Folder Structure
- `src/api/rest/routes/`: Feature-sliced API routers (`voice.py`, `appointments.py`, `twilio_verify.py`).
- `src/control/voice_assistance/`: State graphs, transcribers and logic nodes forming the AI agent.
- `src/core/services/`: Traditional backend API execution units.
- `src/data/models/`: Internal ORM abstractions mapping scheduling entities.
- `docs/`: Technical guides, including agentic architecture references (`AGENTIC.md`).

## Setup Instructions
1. **Install Dependencies**: using `uv pip install -e .[dev]`
2. **Environment Configuration**: Set `.env` referencing `GROQ_API_KEYS`, `TWILIO_SID`, and DB uris.
3. **Database Syncing**: Execute `alembic upgrade head`.
4. **Boot Up**: Run `uvicorn src.api.rest.app:app --host 0.0.0.0 --port 8001 --reload`

## Key Features
- **Voice Appointments**: Automated inbound/outbound telephonic booking agents.
- **Calendar Mgmt**: Slot discovery and reservation collision protection.
- **OTP Verification**: Native integration with Twilio Verify systems.
