"""Embedding helpers for retrieving similar prior table understandings.

Only a small part of the agent needs embeddings: vector search over prior
``table_understandings`` documents. Keeping that logic in one module makes it
easy to swap providers or to short-circuit everything in dry-run mode.
"""

import os

from dotenv import load_dotenv
from voyageai import Client

from . import mocks

load_dotenv()

VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3")

_voyage: Client | None = None


def client() -> Client:
    """Lazily create and cache the Voyage client."""
    global _voyage
    if _voyage is None:
        _voyage = Client(api_key=os.getenv("VOYAGE_API_KEY"))
    return _voyage


def embed(text: str) -> list[float]:
    """Embed a single text string for vector search.

    Dry-run mode returns a deterministic pseudo-vector so vector-search-driven
    logic can still be exercised in local demos.
    """
    if mocks.is_dry_run():
        return mocks.mock_embedding(text)
    r = client().embed(texts=[text], model=VOYAGE_MODEL)
    return r.embeddings[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings in a single API request.

    This helper is currently unused by the main graph but keeps the embedding
    interface complete for future bulk indexing or migration scripts.
    """
    if mocks.is_dry_run():
        return [mocks.mock_embedding(t) for t in texts]
    r = client().embed(texts=texts, model=VOYAGE_MODEL)
    return r.embeddings
