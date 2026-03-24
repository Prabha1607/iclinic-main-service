import asyncio
import logging
from src.control.voice_assistance.prompts.clarify_node_prompt import (
    CLARIFY_SYSTEM_PROMPT,
    COVERAGE_CHECK_HUMAN_TEMPLATE,
    COVERAGE_CHECK_SYSTEM_PROMPT,
    FALLBACK_RESPONSE,
    REASON_SYSTEM_PROMPT,
    TOPICS,
    build_catalogue_lines,
    build_conversation_string,
)
from src.control.voice_assistance.prompts.emergency_prompt import (
    EMERGENCY_RESPONSE,
    EMERGENCY_SYSTEM_PROMPT,
)
from src.control.voice_assistance.prompts.mapping_node_prompt import (
    CLASSIFIER_SYSTEM_PROMPT,
    DEFAULT_INTENT,
    MAPPING_SYSTEM_PROMPT,
)
from src.control.voice_assistance.utils.llm_utils import (
    invokeLargeLLM,
    invokeLLM,
    invokeLLM_json,
    is_emergency
)
from src.control.voice_assistance.utils.state_utils import update_state
from src.control.voice_assistance.utils.common import normalise

logger = logging.getLogger(__name__)


def _fallback_type(appointment_types: dict) -> tuple[int, str]:
    if not appointment_types:
        return -1, DEFAULT_INTENT
    for type_id, (name, _) in appointment_types.items():
        if "general" in name.lower():
            return type_id, normalise(name)
    first_id = next(iter(appointment_types))
    return first_id, normalise(appointment_types[first_id][0])


def _build_greeting(user_name: str | None) -> str:
    name_part = f", {user_name}" if user_name else ""
    return (
        f"Hi{name_part}! Thanks for confirming — I just need to ask you a few quick "
        f"questions before we get you booked in. "
    )


def _is_clarify_active(history: list[dict]) -> bool:
    return any(turn.get("role") == "assistant" for turn in history)


async def _classify_intent(conversation_str: str, appointment_types: dict) -> str:
    catalogue = build_catalogue_lines(appointment_types)
    user_prompt = f"""Appointment type catalogue:
{catalogue}

Full intake conversation:
{conversation_str}

Based on the full conversation above, classify the patient into the most appropriate appointment type.
Return JSON with key "intent" only."""

    parsed = await invokeLLM_json(MAPPING_SYSTEM_PROMPT, user_prompt)
    if not parsed:
        return DEFAULT_INTENT

    intent = str(parsed.get("intent", DEFAULT_INTENT)).strip().lower()
    valid_intents = [normalise(name) for _, (name, _) in appointment_types.items()]
    return intent if intent in valid_intents else DEFAULT_INTENT


async def _resolve_appointment_type_id(intent: str, appointment_types: dict) -> int:
    catalogue = build_catalogue_lines(appointment_types)
    user_prompt = f"""Given the following appointment type catalogue:
{catalogue}

The patient has been classified with intent: "{intent}"

Return ONLY a JSON object with the single key "appointment_type_id" containing the integer ID
that best matches the intent. If nothing matches, use the ID for general check-up.

Example: {{"appointment_type_id": 3}}"""

    parsed = await invokeLLM_json(CLASSIFIER_SYSTEM_PROMPT, user_prompt)
    if not parsed or parsed.get("appointment_type_id") is None:
        fallback_id, _ = _fallback_type(appointment_types)
        return fallback_id

    return int(parsed["appointment_type_id"])


async def _extract_reason(conversation_str: str) -> str:
    response = await invokeLLM(REASON_SYSTEM_PROMPT, f"Conversation:\n{conversation_str}")
    if not response:
        return ""
    return response.strip('"').strip("'")


async def _run_mapping(
    conversation_str: str, appointment_types: dict
) -> tuple[int, str, str]:
    """
    Concurrently classifies appointment intent and extracts reason for visit,
    then resolves the intent to an appointment type ID.

    Falls back to the default appointment type on timeout or any failure.

    Args:
        conversation_str: Full serialised clarification conversation.
        appointment_types: Available appointment types keyed by ID.

    Returns:
        Tuple of (appointment_type_id, intent, reason_for_visit).
    """
    try:
        intent, reason_for_visit = await asyncio.wait_for(
            asyncio.gather(
                _classify_intent(conversation_str, appointment_types),
                _extract_reason(conversation_str),
            ),
            timeout=5.0,
        )
        appointment_type_id = await asyncio.wait_for(
            _resolve_appointment_type_id(intent, appointment_types),
            timeout=3.0,
        )
        return appointment_type_id, intent, reason_for_visit

    except TimeoutError:
        logger.warning("_run_mapping: timed out, using fallback appointment type")
    except Exception as e:
        logger.error("_run_mapping: unexpected error", extra={"error": str(e)})

    fallback_id, fallback_intent = _fallback_type(appointment_types)
    return fallback_id, fallback_intent, ""


async def get_covered_topics(history: list[dict], topics: list[str]) -> list[str]:
    unchecked_numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    conversation = build_conversation_string(history)
    user_prompt = COVERAGE_CHECK_HUMAN_TEMPLATE.format(
        conversation=conversation,
        topics_numbered=unchecked_numbered,
    )

    raw = await invokeLLM(COVERAGE_CHECK_SYSTEM_PROMPT, user_prompt)
    if not raw or raw.upper() == "NONE":
        return []

    return [
        topics[int(n.strip()) - 1]
        for n in raw.upper().split(",")
        if n.strip().isdigit() and 0 <= int(n.strip()) - 1 < len(topics)
    ]


async def _refresh_covered_topics(history: list[dict], covered: list[str]) -> list[str]:
    unchecked = [t for t in TOPICS if t not in covered]
    if not unchecked:
        return covered

    newly_covered = await get_covered_topics(history, unchecked)
    result = list(covered)
    for t in TOPICS:
        if t in newly_covered and t not in result:
            result.append(t)
    return result


def _build_clarify_messages(history: list[dict], uncovered: list[str]) -> list[dict]:
    seed = history if history else [{"role": "user", "content": "start"}]
    return [
        {
            "role": "system",
            "content": CLARIFY_SYSTEM_PROMPT.format(
                next_topic=uncovered[0],
                remaining_count=len(uncovered),
            ),
        },
        *seed,
    ]


async def clarify_node(state: dict) -> dict:
    """
    Drives the symptom clarification phase of the appointment booking flow.

    On each invocation this node:
      1. Appends the latest user utterance to conversation history.
      2. Checks for an emergency and short-circuits if one is detected.
      3. Concurrently generates an LLM clarification response and refreshes
         the set of covered topics.
      4. Once all topics are covered, runs intent classification and reason
         extraction, then marks clarification as complete with a bridge message.
      5. If topics remain, returns the LLM response (prepending a greeting on
         the first turn).

    Falls back to FALLBACK_RESPONSE and marks clarification complete on any
    unhandled exception.

    Args:
        state: Graph state containing:
            - speech_user_text: Latest user utterance.
            - clarify_conversation_history: Prior clarification turns.
            - clarify_covered_topics: Topics already confirmed as covered.
            - identity_user_name: Patient name for greeting personalisation.
            - appointment_types: Available appointment types keyed by ID.
            - mapping_history: Cross-node history used for intent mapping.

    Returns:
        Updated state with:
            - active_node: Set to "clarify".
            - speech_ai_text: AI response or fallback message.
            - clarify_conversation_history: Appended conversation history.
            - clarify_covered_topics: Updated list of covered topics.
            - clarify_completed: True once all topics are covered or on error.
            - mapping_intent: Resolved intent (when completed).
            - mapping_appointment_type_id: Resolved type ID (when completed).
            - mapping_appointment_type_completed: True when mapping is done.
            - booking_reason_for_visit: Extracted reason (when completed).
            - mapping_emergency: True if an emergency was detected.
            - speech_error: Present if an unhandled exception occurred.
    """
    try:
        history: list[dict] = list(state.get("clarify_conversation_history") or [])
        user_text: str | None = state.get("speech_user_text")
        covered: list[str] = list(state.get("clarify_covered_topics") or [])
        user_name: str | None = state.get("identity_user_name")
        appointment_types: dict = state.get("appointment_types") or {}
        mapping_history: list[dict[str, str]] = list(state.get("mapping_history") or [])
        is_first_turn = len(history) == 0
        full_content = ""

        if user_text:
            user_text = user_text.strip()
            history.append({"role": "user", "content": user_text})
            mapping_history.append({"role": "user", "content": user_text})

            if _is_clarify_active(history) and await is_emergency(
                user_text, system_prompt=EMERGENCY_SYSTEM_PROMPT
            ):
                logger.warning("clarify_node: emergency detected, short-circuiting")
                return update_state(
                    state,
                    active_node="clarify",
                    speech_ai_text=EMERGENCY_RESPONSE,
                    mapping_emergency=True,
                    clarify_completed=True,
                    clarify_conversation_history=history,
                    clarify_covered_topics=covered,
                    mapping_history=mapping_history,
                )

            uncovered_optimistic = [t for t in TOPICS if t not in covered]
            if uncovered_optimistic:
                messages = _build_clarify_messages(history, uncovered_optimistic)
                covered, full_content = await asyncio.gather(
                    _refresh_covered_topics(history, covered),
                    invokeLargeLLM(messages),
                )
            else:
                covered = await _refresh_covered_topics(history, covered)

        uncovered = [t for t in TOPICS if t not in covered]

        if not uncovered:
            conversation_str = build_conversation_string(history)

            if appointment_types:
                appointment_type_id, intent, reason_for_visit = await _run_mapping(
                    conversation_str, appointment_types
                )
            else:
                appointment_type_id, intent = _fallback_type(appointment_types)
                reason_for_visit = ""

            friendly_name = intent.replace("_", " ").title()
            bridge_text = (
                f"Thank you for sharing that! I'll go ahead and look into booking "
                f"a {friendly_name} appointment for you now."
            )
            mapping_history.append({"role": "assistant", "content": bridge_text})

            logger.info(
                "clarify_node: all topics covered, mapping complete",
                extra={"intent": intent, "appointment_type_id": appointment_type_id},
            )
            return update_state(
                state,
                active_node="clarify",
                clarify_conversation_history=history,
                clarify_covered_topics=covered,
                clarify_completed=True,
                mapping_intent=intent,
                mapping_appointment_type_id=appointment_type_id,
                mapping_appointment_type_completed=True,
                booking_reason_for_visit=reason_for_visit,
                speech_ai_text=bridge_text,
                mapping_history=mapping_history,
            )

        if not full_content:
            messages = _build_clarify_messages(history, uncovered)
            full_content = await invokeLargeLLM(messages)

        if not full_content:
            logger.warning("clarify_node: LLM returned no content, using fallback response")
            full_content = FALLBACK_RESPONSE

        ai_text = full_content.strip().strip('"').strip("'")

        if is_first_turn:
            ai_text = _build_greeting(user_name) + ai_text

        history.append({"role": "assistant", "content": ai_text})
        logger.info("clarify_node: response generated", extra={"topics_remaining": len(uncovered)})

        return update_state(
            state,
            active_node="clarify",
            speech_ai_text=ai_text,
            clarify_conversation_history=history,
            clarify_covered_topics=covered,
            clarify_completed=False,
        )

    except Exception as exc:
        logger.error("clarify_node: unhandled exception", extra={"error": str(exc)})
        return update_state(
            state,
            active_node="clarify",
            speech_ai_text=FALLBACK_RESPONSE,
            clarify_completed=True,
            speech_error=str(exc),
        )