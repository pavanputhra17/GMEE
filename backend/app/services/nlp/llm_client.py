import json
import logging
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
