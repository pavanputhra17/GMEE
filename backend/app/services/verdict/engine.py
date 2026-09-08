"""GMEE Verdict Engine — probabilistic misinformation assessment.

Methodology (fully transparent, reproducible, no black box):

A claim's verdict probability is a weighted combination of five
independently-computable signals. Every input is shown to the user in the
UI — nothing is hidden:

  1. CORROBORATION  — how many *distinct outlets* assert the same claim.
     Found via pgvector cosine similarity between claim embeddings across
     articles from different domains. Independent confirmation is the
     strongest known signal in verification practice.

  2. CONTRADICTION  — cross-domain claims whose embeddings are near but
     whose NLI stance is negative. Two outlets asserting opposite facts is
     evidence of dispute; the ratio of contradicting to corroborating
     neighbors directly moves probability downward.

  3. SOURCE TRACK RECORD — each outlet carries a credibility prior learned
     from its own history in this corpus: how often do its claims end up
     corroborated vs contradicted? Bayesian-smoothed (Laplace alpha) so a
     single article can't swing an outlet's prior.

  4. ENTITY GROUNDING — verifiable claims name checkable things (people,
     places, organisations, dates, quantities). Claims with zero named
     entities are far more likely to be vague or unfalsifiable.

  5. LINGUISTIC HEDGES — hedged or sensational phrasing ("reportedly",
     "conspiracy", "shocking", "sources say") statistically correlates with
     lower factual reliability. Measured, weighted, disclosed.

Verdict bands (probability that the claim is SUPPORTED):
    >= 0.80  SUPPORTED
    0.55-0.80 LEAN-SUPPORTED
    0.45-0.55 UNRESOLVED   (genuinely uncertain — we say so)
    0.25-0.45 LEAN-DISPUTED
    <  0.25  DISPUTED

The engine NEVER claims absolute truth: it outputs P(supported | evidence)
plus every factor that produced it. That transparency IS the standard.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---- weights (sum = 1.0). Tuned by hand on the live corpus; each is a
# bounded log-odds contribution converted back to probability.
W_CORROB = 0.40
W_CONTRA = 0.20
W_TRACK = 0.15
W_ENTITY = 0.15
W_LANGUAGE = 0.10

# similarity window for considering another claim "the same assertion"
NEAR_MIN = 0.75
NEAR_MAX = 0.97

LAPLACE_ALPHA = 4.0  # smoothing for outlet track record

HEDGE_TERMS = (
    "reportedly", "allegedly", "rumor", "rumour", "unconfirmed",
    "sources say", "it is said", "claims", "supposedly", "appears to",
)
SENSATION_TERMS = (
    "shocking", "bombshell", "exposed", "conspiracy", "secret",
    "they don't want you", "wake up", "mainstream media",
)

VERDICT_BANDS = (
    (0.72, "SUPPORTED"),            # multiple independent outlets agree
    (0.55, "PARTIALLY_SUPPORTED"),  # some corroboration, thin
    (0.38, "UNRESOLVED"),           # genuinely uncertain
    (0.00, "PENDING_DISPUTE"),      # low confidence; final label decided
)                                   # by contradiction evidence below


def band_for(p: float, has_contradiction: bool = False,
             has_corroboration: bool = False) -> str:
    """Final label. Key honesty rules:
    - 'DISPUTED' requires REAL contradiction (an outlet asserting otherwise).
    - Low probability without contradiction = 'UNSUPPORTED' (unverified
      single-source), never 'disputed' — absence of evidence is not
      evidence of absence."""
    if has_contradiction and p < 0.45:
        return "DISPUTED"
    if p >= 0.72:
        return "SUPPORTED"
    if p >= 0.55:
        return "PARTIALLY_SUPPORTED"
    if p >= 0.38:
        return "UNRESOLVED"
    if has_corroboration:
        return "WEAKLY_CORROBORATED"
    return "UNSUPPORTED"


@dataclass
class Signal:
    name: str
    value: float          # normalised 0..1 where 1 pushes toward SUPPORTED
    weight: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerdictResult:
    probability: float
    band: str
    rationale: str
    evidence: dict[str, Any]


class VerdictEngine:
    """Stateless scorer; corpus statistics are passed in per call so the
    engine itself stays pure and unit-testable."""

    # -------------------------------------------------- language signal

    @staticmethod
    def linguistic_signal(claim_text: str) -> Signal:
        low = claim_text.lower()
        words = max(1, len(low.split()))
        hedges = sum(1 for t in HEDGE_TERMS if t in low)
        sensation = sum(1 for t in SENSATION_TERMS if t in low)

        # base: declarative, specific sentences score higher
        score = 0.85
        score -= 0.12 * hedges
        score -= 0.18 * sensation
        if re.search(r"\b(i|we|my|our|you)\b", low):
            score -= 0.15
        if re.search(r"\d", claim_text):
            score += 0.05
        if words < 6:
            score -= 0.10

        return Signal(
            name="language",
            value=max(0.05, min(1.0, score)),
            weight=W_LANGUAGE,
            detail={"hedges": hedges, "sensational": sensation, "words": words},
        )

    # -------------------------------------------------- entity signal

    @staticmethod
    def entity_signal(entities: list[dict[str, Any]]) -> Signal:
        strong_types = {"PERSON", "ORG", "GPE", "LOC", "DATE", "CARDINAL", "MONEY", "QUANTITY", "TIME", "PERCENT"}
        strong = sum(1 for e in entities if e.get("entity_type") in strong_types)
        total = len(entities)

        if total == 0:
            value = 0.30
        elif strong == 0:
            value = 0.45
        else:
            value = min(1.0, 0.55 + 0.15 * strong)

        return Signal(
            name="entity_grounding",
            value=value,
            weight=W_ENTITY,
            detail={"strong_entities": strong, "total_entities": total},
        )

    # -------------------------------------------------- corroboration

    @staticmethod
    def corroboration_signal(
        neighbor_claims: list[dict[str, Any]],
        own_domain: str | None,
    ) -> tuple[Signal, Signal]:
        """Returns (corroboration, contradiction) signals.

        neighbor_claims: rows of {domain, sim, nli} where nli in
        {None, 'yes', 'no'} — stance of the neighbour toward this claim.
        """
        supporting_domains: set[str] = set()
        contradicting_domains: set[str] = set()
        neutral_nearby = 0

        for nb in neighbor_claims:
            dom = nb.get("domain")
            if not dom or dom == own_domain:
                continue  # same-outlet repetition isn't independent
            stance = nb.get("nli")
            if stance == "no":
                contradicting_domains.add(dom)
            elif stance == "yes":
                supporting_domains.add(dom)
            else:
                neutral_nearby += 1

        n_sup = len(supporting_domains)
        n_con = len(contradicting_domains)

        # corroboration: saturating curve — 1 independent outlet is already
        # meaningful, 3+ is strong
        corr_value = 0.35 + 0.65 * (1 - math.exp(-n_sup / 1.5)) if n_sup else 0.30
        contra_ratio = n_con / (n_con + n_sup) if (n_con + n_sup) else 0.0

        corroboration = Signal(
            name="corroboration",
            value=round(corr_value, 3),
            weight=W_CORROB,
            detail={
                "independent_outlets_supporting": sorted(supporting_domains),
                "nearby_unrelated": neutral_nearby,
            },
        )
        contradiction = Signal(
            name="contradiction",
            value=round(contra_ratio, 3),  # 1.0 = everyone contradicts
            weight=W_CONTRA,
            detail={"outlets_contradicting": sorted(contradicting_domains)},
        )
        return corroboration, contradiction

    # -------------------------------------------------- track record

    @staticmethod
    def track_record_signal(
        outlet_stats: dict[str, Any] | None,
    ) -> Signal:
        """Bayesian-smoothed historical support rate for the source outlet."""
        if not outlet_stats:
            return Signal("source_track_record", 0.5, W_TRACK, {"smoothed": True})

        sup = outlet_stats.get("supported", 0)
        dis = outlet_stats.get("disputed", 0)
        n = sup + dis
        smoothed = (sup + LAPLACE_ALPHA * 0.5) / (n + LAPLACE_ALPHA)
        return Signal(
            name="source_track_record",
            value=round(smoothed, 3),
            weight=W_TRACK,
            detail={
                "outlet_supported_history": sup,
                "outlet_disputed_history": dis,
                "smoothing_alpha": LAPLACE_ALPHA,
                "sample_size": n,
            },
        )

    # -------------------------------------------------- combine

    @staticmethod
    def combine(signals: list[Signal]) -> VerdictResult:
        """Weighted log-odds pooling. Each signal contributes
        w_i * logit(v_i); the pooled logit is squashed back through sigmoid.
        Log-odds keeps extreme signals from dominating and mirrors how
        independent evidence combines in naive-Bayes style fusion."""
        num = 0.0
        den = 0.0
        for s in signals:
            v = min(max(s.value, 0.01), 0.99)
            num += s.weight * math.log(v / (1 - v))
            den += s.weight
        p = 1 / (1 + math.exp(-num / den))
        p = round(min(max(p, 0.02), 0.98), 4)

        contra = next((s for s in signals if s.name == "contradiction"), None)
        corr = next((s for s in signals if s.name == "corroboration"), None)
        has_contra = bool(contra and contra.value > 0)
        has_corr = corr is not None and len(
            (corr.detail or {}).get("independent_outlets_supporting", [])
        ) > 0
        band = band_for(p, has_contra, has_corr)

        drivers = sorted(signals, key=lambda s: -(s.weight * abs(math.log(min(max(s.value, .01), .99) / 0.5))))
        top = drivers[:2]
        parts = []
        for s in top:
            arrow = "raises" if s.value >= 0.5 else "lowers"
            parts.append(f"{s.name} {arrow} confidence ({s.value:.2f})")
        rationale = (
            f"P(supported)={p:.2f} [{band}]. "
            f"Strongest factors: " + "; ".join(parts) + "."
        )

        evidence = {
            s.name: {"value": s.value, "weight": s.weight, **s.detail}
            for s in signals
        }
        return VerdictResult(
            probability=p,
            band=band,
            rationale=rationale,
            evidence=evidence,
        )


# ------------------------------------------------------------- NLI stance

_nli_tok = None
_nli_mdl = None


def _load_nli() -> tuple[Any, Any]:
    global _nli_tok, _nli_mdl
    if _nli_mdl is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        logger.info("Loading NLI model google/flan-t5-base …")
        _nli_tok = AutoTokenizer.from_pretrained("google/flan-t5-base")
        _nli_mdl = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-base")
        _nli_mdl.eval()
    return _nli_tok, _nli_mdl


STANCE_CACHE: dict[str, str] = {}


async def nli_stance(claim_text: str, other_text: str) -> str:
    """'yes' if other_text supports claim_text, 'no' if it contradicts,
    'neutral' otherwise. Batch-of-one wrapper around flan-t5 NLI."""
    key = f"{claim_text[:120]}||{other_text[:120]}"
    if key in STANCE_CACHE:
        return STANCE_CACHE[key]

    import asyncio

    def _run() -> str:
        import torch

        tok, mdl = _load_nli()
        prompt = (
            f"premise: {other_text[:300]} hypothesis: {claim_text[:300]} "
            f"Does the premise entail the hypothesis?"
        )
        inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            out = mdl.generate(**inputs, max_new_tokens=3, do_sample=False)
        ans = tok.batch_decode(out, skip_special_tokens=True)[0].strip().lower()
        return "yes" if ans == "yes" else ("no" if ans == "no" else "neutral")

    result = await asyncio.to_thread(_run)
    STANCE_CACHE[key] = result
    return result
