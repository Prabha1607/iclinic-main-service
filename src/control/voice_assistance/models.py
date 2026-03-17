from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_groq import ChatGroq
from sentence_transformers import SentenceTransformer

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

    while attempts < len(API_KEYS):
        api_key = API_KEYS[current_key_index]

        try:
            response = await get_llama3(api_key).ainvoke(messages)
            return response

        except Exception as e:
            last_error = e

            # move to next key
            current_key_index = (current_key_index + 1) % len(API_KEYS)
            attempts += 1

    raise RuntimeError(f"All Groq API keys failed: {last_error}")


async def astream_llm(messages) -> AsyncGenerator[str, None]:

    global current_key_index

    attempts = 0
    last_error = None

    while attempts < len(API_KEYS):
        api_key = API_KEYS[current_key_index]
        try:
            async for chunk in get_llama3(api_key).astream(messages):
                if chunk.content:
                    yield chunk.content
            return
        except Exception as e:
            last_error = e
            current_key_index = (current_key_index + 1) % len(API_KEYS)
            attempts += 1

    raise RuntimeError(f"All Groq API keys failed during streaming: {last_error}")


class SentenceTransformerEmbeddings(Embeddings):
    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5"):
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()


def get_embedding_model():
    return SentenceTransformerEmbeddings(model_name="BAAI/bge-base-en-v1.5")
