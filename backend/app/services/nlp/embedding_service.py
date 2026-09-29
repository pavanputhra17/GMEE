import logging

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _model: SentenceTransformer | None = None

    @classmethod
    def load_model(cls) -> None:
        """Called during app lifespan to load the model once."""
        if cls._model is None:
            model_name = get_settings().EMBEDDING_MODEL
            logger.info("Loading SentenceTransformer model %s...", model_name)
            # We don't strictly need PyTorch if we have ONNX, but SentenceTransformers
            # usually defaults to PyTorch backend.
            cls._model = SentenceTransformer(model_name)
            logger.info("SentenceTransformer model loaded.")

    @classmethod
    def model_name(cls) -> str:
        return get_settings().EMBEDDING_MODEL

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        if cls._model is None:
            cls.load_model()

        # The model automatically truncates to its max_seq_length
        # (384 for all-mpnet-base-v2).
        # It returns a numpy array, we convert to list of floats for pgvector.
        embedding = cls._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return [float(x) for x in embedding]
