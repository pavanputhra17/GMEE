import logging
import threading
from typing import Any

import httpx
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _model: SentenceTransformer | None = None
    _lock = threading.Lock()

    @classmethod
    def load_model(cls) -> None:
        """Load the model once (idempotent, thread-safe).

        Skipped when HUGGINGFACE_API_KEY is set: embeddings come from the
        Inference API instead, saving the ~420 MB local model on small hosts.

        Called by the background warm-up task and by pipeline jobs. Request
        handlers must NOT call this: loading takes seconds and blocks.
        """
        if get_settings().HUGGINGFACE_API_KEY:
            logger.info(
                "HUGGINGFACE_API_KEY is set. Using Hugging Face Inference API "
                "instead of local model."
            )
            return
        if cls._model is not None:
            return
        with cls._lock:
            if cls._model is None:
                model_name = get_settings().EMBEDDING_MODEL
                logger.info("Loading SentenceTransformer model %s...", model_name)
                # We don't strictly need PyTorch if we have ONNX, but SentenceTransformers
                # usually defaults to PyTorch backend.
                cls._model = SentenceTransformer(model_name)
                logger.info("SentenceTransformer model loaded.")

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._model is not None

    @classmethod
    def model_name(cls) -> str:
        return get_settings().EMBEDDING_MODEL

    @classmethod
    def generate_embedding(cls, text: str, *, allow_load: bool = False) -> list[float]:
        settings = get_settings()

        # With a key configured, embed via the Inference API to save RAM (the
        # local all-mpnet model is ~420 MB and OOMs small instances).
        if settings.HUGGINGFACE_API_KEY:
            try:
                return _embed_via_hf_api(
                    text, settings.HUGGINGFACE_API_KEY, settings.EMBEDDING_MODEL
                )
            except Exception as e:
                logger.error(
                    "Hugging Face API failed: %s. Falling back to local model.", e
                )

        if cls._model is None:
            if not allow_load:
                raise RuntimeError("Embedding model not loaded. Call load_model() first.")
            cls.load_model()
        if cls._model is None:
            # load_model() was skipped because a key is set but the API call
            # above failed; force the local model rather than fail outright.
            with cls._lock:
                if cls._model is None:
                    cls._model = SentenceTransformer(get_settings().EMBEDDING_MODEL)
        assert cls._model is not None

        # The model automatically truncates to its max_seq_length
        # (384 for all-mpnet-base-v2).
        # It returns a numpy array, we convert to list of floats for pgvector.
        embedding_local = cls._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return [float(x) for x in embedding_local]


def _embed_via_hf_api(text: str, api_key: str, model_name: str) -> list[float]:
    """One-text embedding via the HF feature-extraction pipeline."""
    if "/" not in model_name:
        model_name = f"sentence-transformers/{model_name}"
    api_url = (
        "https://api-inference.huggingface.co/pipeline/feature-extraction/" + model_name
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client() as client:
        response = client.post(
            api_url,
            headers=headers,
            json={"inputs": [text], "options": {"wait_for_model": True}},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()

    def flatten_to_1d(data: Any) -> list[float]:
        # Feature extraction returns nested lists; keep the first flat row.
        if isinstance(data, list):
            if data and isinstance(data[0], float):
                return [float(x) for x in data]
            if data and isinstance(data[0], list):
                return flatten_to_1d(data[0])
        return []

    embedding = flatten_to_1d(result)
    if not embedding:
        raise ValueError(f"Could not parse embedding from API response: {result}")
    return embedding

