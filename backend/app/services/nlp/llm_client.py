import json
import logging
import os
from abc import ABC, abstractmethod

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ExtractedClaim(BaseModel):
    claim_text: str
    confidence: float | None = None


class LLMClient(ABC):
    @abstractmethod
    async def extract_claims(self, article_text: str) -> list[ExtractedClaim]:
        """Returns a list of extracted factual claims. Must return an empty
        list for articles with no extractable factual claims (e.g. opinion
        pieces) — this is a valid, successful result, not a failure."""


class AnthropicLLMClient(LLMClient):
    def __init__(self):
        self.settings = get_settings()
        # Initialize only if API key is provided
        if self.settings.ANTHROPIC_API_KEY:
            self.client = AsyncAnthropic(api_key=self.settings.ANTHROPIC_API_KEY)
        else:
            self.client = None

        self.model = getattr(self.settings, 'LLM_MODEL', 'claude-3-haiku-20240307')

    async def extract_claims(self, article_text: str) -> list[ExtractedClaim]:
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        prompt = f"""
You are an expert fact-checker and information extraction system.
Extract all standalone factual claims from the following text.
If there are no factual claims (e.g. it is pure opinion, or too short), return an empty JSON array.

Guidelines for claims:
- Each claim should be a standalone sentence that can be verified independently.
- Resolve pronouns so the claim makes sense out of context.
- Provide a confidence score between 0.0 and 1.0 representing how clearly the text asserts this claim.

Return ONLY a JSON array of objects, with no markdown formatting, no code blocks, and no preamble.
The JSON objects must have exactly these two keys:
1. "claim_text" (string)
2. "confidence" (number)

Example output format:
[
    {{"claim_text": "The Eiffel Tower is located in Paris, France.", "confidence": 0.99}},
    {{"claim_text": "The company's revenue increased by 15% in Q3 2023.", "confidence": 0.95}}
]

Text to analyze:
{article_text}
"""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            raw_text = response.content[0].text.strip()

            # Try to parse the JSON
            try:
                data = json.loads(raw_text)
                if not isinstance(data, list):
                    raise ValueError("Expected a JSON array")

                claims = []
                for item in data:
                    claims.append(ExtractedClaim.model_validate(item))
                return claims

            except (json.JSONDecodeError, ValidationError, ValueError) as parse_err:
                logger.error(f"Failed to parse LLM response. Error: {parse_err}. Raw response (truncated): {raw_text[:200]}")
                raise ValueError(f"Invalid LLM response format: {parse_err}")

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise


class HuggingFaceLLMClient(LLMClient):
    """Local zero-cost claim extractor backed by an open HF model.

    Runs FLAN-T5-base instruction-tuned model on CPU via transformers'
    text2text pipeline. Same interface as the Anthropic client, so the NLP
    orchestrator can use either transparently. Preference order in
    get_llm_client(): explicit ANTHROPIC key > local HF model.
    """

    MODEL_ID = os.environ.get("HF_LLM_MODEL", "google/flan-t5-base")

    def __init__(self):
        self._pipe = None

    def _load(self):
        if self._pipe is None:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Loading HF claim-extraction model %s …", self.MODEL_ID)
            tok = AutoTokenizer.from_pretrained(self.MODEL_ID)
            mdl = AutoModelForSeq2SeqLM.from_pretrained(self.MODEL_ID)
            mdl.to(device).eval()
            self._pipe = (tok, mdl, device)
            logger.info("HF claim-extraction model loaded.")

    def _split_sentences(self, text: str) -> list[str]:
        import re

        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if 30 < len(p.strip()) < 400]

    def _score_claim(self, sentence: str) -> float:
        """Heuristic confidence from structural verifiability signals."""
        base = 0.5
        if any(ch.isdigit() for ch in sentence):
            base += 0.15
        if any(
            k in sentence.lower()
            for k in ("said", "according to", "announced", "reported", "confirmed", "stated")
        ):
            base += 0.12
        words = sentence.split()
        if len(words) >= 10:
            base += 0.08
        low = f" {sentence.lower()} "
        if any(
            k in low
            for k in (" i ", " my ", " we ", " our ", "think", "feel", "love", "hate", "ridiculous")
        ):
            base -= 0.3
        return round(min(0.97, max(0.05, base)), 2)

    async def extract_claims(self, article_text: str) -> list[ExtractedClaim]:
        import asyncio

        self._load()
        sentences = self._split_sentences(article_text)
        if not sentences:
            return []

        prompts = [
            (
                f'premise: {s} hypothesis: {s} This statement is a factual claim. '
                f'Does the premise entail the hypothesis?'
            )
            for s in sentences[:8]  # cap per-article cost on CPU
        ]

        def run_pipeline():
            import torch

            tok, mdl, device = self._pipe
            inputs = tok(prompts, return_tensors="pt", padding=True, truncation=True, max_length=512)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                out_ids = mdl.generate(**inputs, max_new_tokens=6, do_sample=False)
            decoded = tok.batch_decode(out_ids, skip_special_tokens=True)
            return [{"generated_text": t} for t in decoded]

        try:
            outputs = await asyncio.to_thread(run_pipeline)
        except Exception as e:
            logger.error(f"HF pipeline error: {e}")
            raise

        claims: list[ExtractedClaim] = []
        for sent, out in zip(sentences, outputs):
            if isinstance(out, list):
                out = out[0] if out else {}
            answer = (out.get("generated_text", "") or "").strip().lower()
            confidence = self._score_claim(sent)
            if answer == "yes" and confidence >= 0.5:
                claims.append(ExtractedClaim(claim_text=sent, confidence=confidence))
        return claims


def get_llm_client() -> LLMClient:
    """Factory used by the NLP orchestrator.

    Priority:
      1. Anthropic when ANTHROPIC_API_KEY is set (best quality)
      2. Local HuggingFace model otherwise (zero cost, offline)
         - set LLM_BACKEND=none to force the legacy skip behaviour
    """
    settings = get_settings()
    backend = getattr(settings, "LLM_BACKEND", "") or (
        "anthropic" if settings.ANTHROPIC_API_KEY else "huggingface"
    )
    if backend == "anthropic" and settings.ANTHROPIC_API_KEY:
        return AnthropicLLMClient()
    if backend == "none":
        return _NoOpLLMClient()
    return HuggingFaceLLMClient()


class _NoOpLLMClient(LLMClient):
    """Legacy behaviour: no extraction possible → mark articles skipped."""

    async def extract_claims(self, article_text: str) -> list[ExtractedClaim]:
        return []
