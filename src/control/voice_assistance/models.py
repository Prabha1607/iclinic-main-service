from collections.abc import AsyncGenerator
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from src.config.settings import settings

load_dotenv()

API_KEYS = settings.groq_keys_list

current_key_index = 0


def get_llama3(api_key: str):
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        max_tokens=100,
        api_key=api_key,
    )


def get_llama1():
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.2,
        max_tokens=100,
        api_key=API_KEYS[0],
    )


async def ainvoke_llm(messages):

    global current_key_index

    attempts = 0
    last_error = None

    start_index = current_key_index  

    while attempts < len(API_KEYS):
        api_key = API_KEYS[current_key_index]

        try:
            response = await get_llama3(api_key).ainvoke(messages)

            return response

        except Exception as e:
            last_error = e

            current_key_index = (current_key_index + 1) % len(API_KEYS)
            attempts += 1

    raise RuntimeError(f"All Groq API keys failed: {last_error}")
