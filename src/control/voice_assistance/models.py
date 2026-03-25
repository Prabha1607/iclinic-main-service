from dotenv import load_dotenv
from langchain_groq import ChatGroq
from src.config.settings import settings

load_dotenv()

API_KEYS = settings.groq_keys_list

# Separate counters so llama1 and llama3 don't fight over the same index
_llama1_index = 0
_llama3_index = 0


def get_llama1() -> ChatGroq:
    """
    Returns a llama-3.1-8b-instant client, rotating across all API keys
    on every call instead of always pinning to API_KEYS[0].
    """
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
    """Advances the llama3 key index and returns the next key."""
    global _llama3_index
    key = API_KEYS[_llama3_index % len(API_KEYS)]
    _llama3_index = (_llama3_index + 1) % len(API_KEYS)
    return key


async def ainvoke_llm(messages):
    """
    Invokes llama-3.3-70b-versatile with proactive key rotation on every call.
    Falls back through remaining keys only on actual exception.
    Raises RuntimeError if all keys are exhausted.
    """
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