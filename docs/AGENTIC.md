# Agentic Voice Flow

## What is the Agentic Flow
The `main-service` utilizes an autonomous AI voice-assistant built on top of **LangGraph**, **Twilio Voice**, and **Large Language Models (LLMs)**. Instead of following rigid DTMF trees ("Press 1 for X"), the agent maintains an evolving conversation state, decides what questions to ask next dynamically, and synthesizes speech payloads back to the caller in real time.

## Flow Design
The execution heavily relies on a state machine pattern driven by LangGraph:
1. **Initiation (`/make-call`)**: Fetches schedule dependencies (e.g. Appointment Types) from the database and constructs the `initial_state` memory context. The `call_graph` is invoked to map the target number and dial out.
2. **Transcription (`/voice-response`)**: Caller speech is transcribed automatically via Twilio's `<Gather>` node and sent back to the webhook as the `SpeechResult`.
3. **Graph Evaluation**: The `response_graph.ainvoke(state)` triggers:
   - Evaluates caller intent (Booking vs Support vs Emergency).
   - Looks up internal PostgreSQL registries if availability checking is requested.
   - Generates the `ai_text` response (routed via LLM processing nodes).
4. **Synthesis & Action**: 
   - Generates synchronous TwiML wrapping the `ai_text` for Text-To-Speech (TTS).
   - If `call_complete` is flagged by the graph, it explicitly instructs Twilio to hang up, effectively ending the agent's context lifecycle.
   - If an `emergency` intent is detected, the `ai_text` is spoken and the call is immediately dialed (`<Dial>`) to an `EMERGENCY_FORWARD_NUMBER`.

## State Management
State (`state: dict`) functions as the persistent memory payload moving between discrete webhooks. 
It spans both services inherently but is stored in PostgreSQL via the `session_store.py` subsystem keyed by the Twilio `call_sid`. Before every graph node execution, the session is loaded, updated with the new `SpeechResult`, and re-persisted post-evaluation. 

### Key context variables:
- `identity_patient_id`, `identity_user_name` (Verified via `auth-service` token parsing)
- `speech_user_text` (Current caller transcript)
- `speech_ai_text` (Generated reply)
- `mapping_emergency` (Boolean flag)
- `slot_booked_id` (Transactional result identifier)

## Example Lifecycle
1. User requests a call targeting "+1234567890" containing a valid Bearer token.
2. Agent dials out and synthesizes: "Hello Jane, how can I assist you with your clinic booking?"
3. User: "I need to come in for a checkup tomorrow."
4. Hook strikes `/voice-response` with `SpeechResult="I need to come in for a checkup tomorrow."`.
5. The specific node resolving `appointment_types` parses the transcription.
6. The responder node checks `db`, finds an open slot, and sets `slot_booked_id=20`.
7. Graph sets `ai_text="I've got you booked. Goodbye."`, flags `identity_confirmation_completed=True`.
8. TwiML synthesizes the text, updates the DB, and hangs up the receiver.
