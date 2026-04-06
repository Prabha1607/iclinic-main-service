import asyncio
import logging
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.control.voice_assistance.graph import build_response_graph
from src.control.voice_assistance.utils.state_utils import fresh_state
from src.core.services.appointment_types import get_appointment_types
from src.data.clients.postgres_client import AsyncSessionLocal

logger = logging.getLogger(__name__)

response_graph = build_response_graph()


def _build_appointment_types(appointment_types: list) -> dict:
    return {
        at.id: (at.name, at.description or "")
        for at in appointment_types
        if at.is_active
    }


async def chat_loop():
    async with AsyncSessionLocal() as db:
        appointment_types_raw = await get_appointment_types(db)

    built_appointment_types = _build_appointment_types(appointment_types_raw)
    logger.info(
        f"[debug] loaded {len(built_appointment_types)} appointment types: {list(built_appointment_types.keys())}"
    )

    state = fresh_state(
        call_to_number="debug",
        call_sid="debug123",
        identity_user_name="prabha",
        identity_user_phone="9524650818",
        identity_user_email="prabhamuruganantham06@gmail.com",
        appointment_types=built_appointment_types,
    )

    state["identity_confirmation_completed"] = True
    state["identity_confirmed_user"] = True
    state["identity_patient_id"] = 5
    while True:
        user_input = input("User: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            break

        state["speech_user_text"] = user_input

        result = await response_graph.ainvoke(state)

        ai_text = result.get("speech_ai_text")
        logger.info("AI: %s", ai_text)

        state = result


if __name__ == "__main__":
    asyncio.run(chat_loop())
