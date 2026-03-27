from dotenv import load_dotenv
from langchain_groq import ChatGroq
from src.config.settings import settings

load_dotenv()

API_KEYS = settings.groq_keys_list

_llama1_index = 0
_llama3_index = 0


def get_llama1() -> ChatGroq:
    
    global _llama1_index
    key = API_KEYS[_llama1_index % len(API_KEYS)]
    _llama1_index = (_llama1_index + 1) % len(API_KEYS)
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.2,
        max_tokens=1000,
        api_key=key,
    )


def _next_llama3_key() -> str:
    global _llama3_index
    key = API_KEYS[_llama3_index % len(API_KEYS)]
    _llama3_index = (_llama3_index + 1) % len(API_KEYS)
    return key


async def ainvoke_llm(messages):
   
    attempts = 0
    last_error = None

    while attempts < len(API_KEYS):
        api_key = _next_llama3_key()
        try:
            return await ChatGroq(
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                max_tokens=1000,
                api_key=api_key,
            ).ainvoke(messages)
        except Exception as e:
            last_error = e
            attempts += 1

    raise RuntimeError(f"All Groq API keys failed: {last_error}")