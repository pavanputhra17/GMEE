"""HuggingFaceLLMClient: sentence filtering, claim scoring, batched extract."""
from typing import Any

from app.services.nlp.llm_client import (
    HuggingFaceLLMClient,
    _NoOpLLMClient,
    get_llm_client,
)


class FakeTensor(list[list[int]]):
    """Mimics torch.Tensor: a list subclass whose .to(device) is a no-op.

    Wraps the whole 2D batch (list-of-rows), matching how real HF
    tokenizers return a single BatchEncoding of tensors, not lists.
    """

    def to(self, device: str) -> "FakeTensor":
        return self


class FakeTokenizer:
    def __call__(self, prompts, return_tensors="pt", **kw):
        rows = [[1] * 8 for _ in prompts]
        return {
            "input_ids": FakeTensor(rows),
            "attention_mask": FakeTensor(rows),
        }

    def batch_decode(self, ids, skip_special_tokens=True):
        return ["yes"] * len(ids)


class FakeModel:
    def generate(self, **kw: Any) -> Any:
        return kw["input_ids"]


def test_split_sentences_enforces_length_bounds():
    c = HuggingFaceLLMClient()
    text = (
        "Short. "  # too short
        "This is a perfectly reasonable declarative sentence with several words and no drama. "  # kept
        "Too long: " + ("word " * 120)  # >400 chars → dropped
    )
    out = c._split_sentences(text)
    assert len(out) == 1
    assert out[0].startswith("This is a perfectly")


def test_score_claim_rewards_verifiable_language():
    c = HuggingFaceLLMClient()
    factual = "The agency reported a 15 percent increase in 2023 according to records."
    subjective = "I think this whole thing feels ridiculous and I hate it a lot, honestly speaking."
    assert c._score_claim(factual) >= 0.6
    assert c._score_claim(subjective) < 0.4


async def test_extract_claims_accepts_factual_rejects_subjective():
    c = HuggingFaceLLMClient()
    c._pipe = (FakeTokenizer(), FakeModel(), "cpu")
    text = (
        "The agency reported a 15 percent increase in March according to official records. "
        "I think this whole situation feels ridiculous and personally I hate it, honestly. "
    )
    claims = await c.extract_claims(text)
    assert len(claims) == 1
    assert claims[0].claim_text.startswith("The agency reported")
    assert claims[0].confidence is not None and claims[0].confidence >= 0.5


async def test_noop_client_returns_empty_and_factory_respects_backend(monkeypatch):
    noop = _NoOpLLMClient()
    assert await noop.extract_claims("anything") == []

    # The factory reads config through module-level get_settings(); stub it
    # with a lightweight namespace (Settings has no LLM_BACKEND field).
    from types import SimpleNamespace

    from app.services.nlp import llm_client as lc

    monkeypatch.setattr(
        lc,
        "get_settings",
        lambda: SimpleNamespace(ANTHROPIC_API_KEY="", LLM_BACKEND="none"),
    )
    assert isinstance(get_llm_client(), _NoOpLLMClient)
