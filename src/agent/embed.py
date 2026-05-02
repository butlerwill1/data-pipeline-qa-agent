import os

from dotenv import load_dotenv
from voyageai import Client

from . import mocks

load_dotenv()

VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3")

_voyage: Client | None = None


def client() -> Client:
    global _voyage
    if _voyage is None:
        _voyage = Client(api_key=os.getenv("VOYAGE_API_KEY"))
    return _voyage


def embed(text: str) -> list[float]:
    if mocks.is_dry_run():
        return mocks.mock_embedding(text)
    r = client().embed(texts=[text], model=VOYAGE_MODEL)
    return r.embeddings[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    if mocks.is_dry_run():
        return [mocks.mock_embedding(t) for t in texts]
    r = client().embed(texts=texts, model=VOYAGE_MODEL)
    return r.embeddings
