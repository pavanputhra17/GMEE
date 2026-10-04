import logging
import threading

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _model: SentenceTransformer | None = None
    _lock = threading.Lock()

    @classmethod
    def load_model(cls) -> None:
        """Load the model once (idempotent, thread-safe).

        Called by the background warm-up task and by pipeline jobs. Request
        handlers must NOT call this: loading takes seconds and blocks.
        """
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
        if cls._model is None:
            if not allow_load:
                raise RuntimeError("Embedding model not loaded. Call load_model() first.")
            cls.load_model()
        assert cls._model is not None

        # The model automatically truncates to its max_seq_length
        # (384 for all-mpnet-base-v2).
        # It returns a numpy array, we convert to list of floats for pgvector.
        embedding = cls._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return [float(x) for x in embedding]
