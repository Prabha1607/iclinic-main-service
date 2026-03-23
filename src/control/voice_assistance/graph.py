from langgraph.graph import END, StateGraph

from src.control.voice_assistance.routes import (
    route_after_cancellation_slot_selection,
    route_after_clarify,
    route_after_doctor_selection,
    route_after_identity_confirmation,
    route_after_pre_confirmation,
    route_after_service_intent,
    route_after_booking_slot_selection,
    route_after_stt,
)

from .nodes.book_appointment_node import book_appointment_node
from .nodes.booking_confirmation_node import booking_confirmation_node
from .nodes.booking_slot_selection_node import booking_slot_selection_node
from .nodes.call_init_node import call_init_node
from .nodes.cancel_appointment_node import cancel_appointment_node
from .nodes.cancel_confirmation_node import cancel_confirmation_node
from .nodes.cancellation_slot_selection_node import cancellation_slot_selection_node
from .nodes.general_assistance_node import general_assistance_node 
from .nodes.clarify_node import clarify_node
from .nodes.doctor_selection_node import doctor_selection_node
from .nodes.identity_confirmation_node import identity_confirmation_node
from .nodes.pre_confirmation_node import pre_confirmation_node
from .nodes.service_intent_node import service_intent_node
from .nodes.stt_node import stt_node
from .nodes.tts_node import tts_node
from .state import VoiceState


def build_call_graph():
    workflow = StateGraph(VoiceState)
    workflow.add_node("call_init", call_init_node)
    workflow.set_entry_point("call_init")
    workflow.add_edge("call_init", END)
    return workflow.compile()



def build_response_graph():

    workflow = StateGraph(VoiceState)

    workflow.add_node("stt", stt_node)
    workflow.add_node("service_intent", service_intent_node)
    workflow.add_node("identity_confirmation", identity_confirmation_node)
    workflow.add_node("clarify", clarify_node)
    workflow.add_node("doctor_selection", doctor_selection_node)
    workflow.add_node("booking_slot_selection", booking_slot_selection_node)
    workflow.add_node("pre_confirmation", pre_confirmation_node)
    workflow.add_node("book_appointment", book_appointment_node)
    workflow.add_node("booking_confirmation", booking_confirmation_node)
    workflow.add_node("cancellation_slot_selection", cancellation_slot_selection_node)
    workflow.add_node("cancel_appointment", cancel_appointment_node)
    workflow.add_node("cancel_confirmation", cancel_confirmation_node)
    workflow.add_node("general_assistance", general_assistance_node)  
    workflow.add_node("tts", tts_node)

    workflow.set_entry_point("stt")

    workflow.add_conditional_edges(
        "stt",
        route_after_stt,
        {
            "service_intent": "service_intent",
            "identity_confirmation": "identity_confirmation",
            "clarify": "clarify",
            "doctor_selection": "doctor_selection",
            "booking_slot_selection": "booking_slot_selection",
            "pre_confirmation": "pre_confirmation",
            "book_appointment": "book_appointment",
            "cancellation_slot_selection": "cancellation_slot_selection",
            "cancel_appointment": "cancel_appointment",
            "general_assistance": "general_assistance",
            "tts": "tts",
        },
    )

    workflow.add_conditional_edges(
        "service_intent",
        route_after_service_intent,
        {
            "identity_confirmation": "identity_confirmation",
            "cancellation_slot_selection": "cancellation_slot_selection",
            "tts": "tts",
        },
    )

    workflow.add_conditional_edges(
        "identity_confirmation",
        route_after_identity_confirmation,
        {"tts": "tts", "clarify": "clarify"},
    )

    workflow.add_conditional_edges(
        "clarify",
        route_after_clarify,
        {"tts": "tts", "doctor_selection": "doctor_selection"},
    )

    workflow.add_conditional_edges(
        "doctor_selection",
        route_after_doctor_selection,
        {"tts": "tts", "booking_slot_selection": "booking_slot_selection"},
    )

    workflow.add_conditional_edges(
        "booking_slot_selection",
        route_after_booking_slot_selection,
        {
            "pre_confirmation": "pre_confirmation",
            "tts": "tts",
        },
    )

    workflow.add_conditional_edges(
        "pre_confirmation",
        route_after_pre_confirmation,
        {
            "book_appointment": "book_appointment",
            "tts": "tts",
        },
    )

    workflow.add_conditional_edges(
        "cancellation_slot_selection",
        route_after_cancellation_slot_selection,
        {
            "cancel_appointment": "cancel_appointment",
            "tts": "tts",
        },
    )

    workflow.add_edge("book_appointment", "booking_confirmation")
    workflow.add_edge("booking_confirmation", "tts")
    workflow.add_edge("cancel_appointment", "cancel_confirmation")
    workflow.add_edge("cancel_confirmation", "tts")
    workflow.add_edge("general_assistance", "tts") 
    workflow.add_edge("tts", END)

    return workflow.compile()