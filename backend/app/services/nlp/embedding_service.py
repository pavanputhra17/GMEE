import logging
import httpx
from typing import Any

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _model: SentenceTransformer | None = None

    @classmethod
    def load_model(cls) -> None:
        """Called during app lifespan to load the model once (if not using API)."""
        settings = get_settings()
        if settings.HUGGINGFACE_API_KEY:
            logger.info("HUGGINGFACE_API_KEY is set. Using Hugging Face Inference API instead of local model.")
            return

        if cls._model is None:
            model_name = settings.EMBEDDING_MODEL
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
        settings = get_settings()
        
        # If API key is provided, use the Inference API to save RAM
        if settings.HUGGINGFACE_API_KEY:
            model_id = settings.EMBEDDING_MODEL
            if "/" not in model_id:
                model_id = f"sentence-transformers/{model_id}"
                
            api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_id}"
            headers = {"Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}"}
            
            try:
                with httpx.Client() as client:
                    response = client.post(
                        api_url,
                        headers=headers,
                        json={"inputs": [text], "options": {"wait_for_model": True}},
                        timeout=30.0
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    # HF feature extraction returns lists of lists. Depending on the model,
                    # it might be [ [ [ ... ] ] ] or [ [ ... ] ].
                    # We want the first 1D array of floats.
                    
                    def flatten_to_1d(data: Any) -> list[float]:
                        if isinstance(data, list):
                            if len(data) > 0 and isinstance(data[0], float):
                                return data
                            if len(data) > 0 and isinstance(data[0], list):
                                return flatten_to_1d(data[0])
                        return []

                    embedding = flatten_to_1d(result)
                    
                    if not embedding:
                        raise ValueError(f"Could not parse embedding from API response: {result}")
                        
                    return [float(x) for x in embedding]
            except Exception as e:
                logger.error("Hugging Face API failed: %s. Falling back to local model.", e)
                # If API fails, we could fallback to local, but on 512MB RAM it will crash.
                # However, for robustness we'll attempt it.

        # Fallback to local model
        if cls._model is None:
            cls.load_model()
            
        if cls._model is None:
             # Only happens if load_model() skipped due to API key but API failed and we somehow got here.
             # Force load without checking key
             cls._model = SentenceTransformer(settings.EMBEDDING_MODEL)

        # The model automatically truncates to its max_seq_length
        # (384 for all-mpnet-base-v2).
        # It returns a numpy array, we convert to list of floats for pgvector.
        embedding_local = cls._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return [float(x) for x in embedding_local]

