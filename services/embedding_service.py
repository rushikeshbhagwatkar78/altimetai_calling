from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

import numpy as np
from dotenv import load_dotenv
from google import genai

load_dotenv()
logger = logging.getLogger("crm_embeddings")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-2").strip()

_client: Optional[genai.Client] = None


def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        if not GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is not configured for embeddings.")
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def generate_embedding(text: str) -> List[float]:
    """Generate normalized vector embedding using Google GenAI embedding model."""
    cleaned = text.strip()
    if not cleaned:
        return [0.0] * 3072

    client = get_genai_client()
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=cleaned,
        )
        vector = response.embeddings[0].values
        # Normalize vector
        vec_np = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(vec_np)
        if norm > 0:
            vec_np = vec_np / norm
        return vec_np.tolist()
    except Exception as e:
        logger.error(f"EMBEDDING_GENERATION_FAILED | model={EMBEDDING_MODEL} | error={e}")
        # Fallback pseudo-embedding if API temporarily unavailable to prevent breaking caller
        return [0.0] * 3072


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
