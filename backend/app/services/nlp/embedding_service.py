import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    _model: SentenceTransformer | None = None

    @classmethod
    def load_model(cls):
        """Called during app lifespan to load the model once."""
        if cls._model is None:
            logger.info("Loading SentenceTransformer model all-mpnet-base-v2...")
            # We don't strictly need PyTorch if we have ONNX, but SentenceTransformers
            # usually defaults to PyTorch backend.
            cls._model = SentenceTransformer("all-mpnet-base-v2")
            logger.info("SentenceTransformer model loaded.")

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        if cls._model is None:
            raise RuntimeError("Embedding model not loaded. Call load_model() first.")
            
        # The model automatically truncates to max_seq_length (384 for all-mpnet-base-v2).
        # We can pass truncation=True to be explicit.
        # It returns a numpy array, we convert to list of floats for pgvector.
        embedding = cls._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        
        # In case the result is 2D (if we passed a list), return the first element.
        # But we passed a string, so it should be a 1D array of floats.
        return embedding.tolist()
