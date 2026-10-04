"""Text/entity features with no labels, embedding scores, or fitted corpus state."""

from __future__ import annotations

import re
from collections.abc import Iterable

FEATURE_VERSION = "gmee-text-features-v1"
_WORD = re.compile(r"\b\w+\b", re.UNICODE)


def lexical_jaccard(text_a: str, text_b: str) -> float:
    a, b = (set(_WORD.findall(t.casefold())) for t in (text_a, text_b))
    return len(a & b) / len(a | b) if a or b else 0.0


def entity_jaccard(entities_a: Iterable[str], entities_b: Iterable[str]) -> float | None:
    a, b = ({e.strip().casefold() for e in values if e.strip()} for values in (entities_a, entities_b))
    # Missing entity evidence is not an assertion that two claims differ.
    return len(a & b) / len(a | b) if a or b else None
