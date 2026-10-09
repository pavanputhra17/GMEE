import difflib
import re
from dataclasses import dataclass, field
from typing import TypedDict

"""Word-level mutation diffing between two versions of a claim.

Pure functions — no DB, no models. Used by the Mutation Diff Inspector
(GET /graph/lineage/{claim_id}) and unit-tested in tests/test_mutation_diff.py.
"""

_TOKEN_RE = re.compile(r"\w+[.,%]?|[^\w\s]")
_NUMBER_RE = re.compile(r"^\$?\d[\d.,]*%?$")

# Hedging / epistemic-stance lexicon. Losing these words between two
# versions of a claim is one of the classic mutation signatures.
HEDGE_WORDS = frozenset({
    "allegedly", "reportedly", "unverified", "claimed", "claims",
    "rumored", "rumour", "rumor", "purportedly", "seemingly", "apparently",
    "may", "might", "could", "possibly", "perhaps", "sources", "according",
    "believed", "suspected", "speculation", "unconfirmed",
})

_STOPWORDS = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "it", "its", "as", "by", "with", "from",
    "that", "this", "has", "have", "had", "not", "no", "but", "will",
    "after", "before", "over", "into", "than", "then", "new", "first",
})


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def _numbers(tokens: list[str]) -> set[str]:
    return {t for t in tokens if _NUMBER_RE.match(t)}


def _entities(tokens: list[str]) -> set[str]:
    """Lightweight capitalized-token entity proxy (no spaCy in the hot path).

    A token is entity-ish if it is Titlecase, longer than 2 chars, not a
    stopword and not a number.
    """
    return {
        t for t in tokens
        if len(t) > 2 and t[:1].isupper() and t.isalpha() and t.lower() not in _STOPWORDS
    }


def _hedges(tokens: list[str]) -> set[str]:
    return {t.lower() for t in tokens if t.lower() in HEDGE_WORDS}


class DiffSegment(TypedDict):
    type: str
    old: str
    new: str
    kinds: list[str]


class MutationDiffResult(TypedDict):
    numeric_changes: list[dict[str, str]]
    entity_changes: list[dict[str, str]]
    hedge_changes: list[dict[str, str]]
    similarity: float
    mutation_types: list[str]
    segments: list[DiffSegment]


@dataclass
class MutationSummary:
    numeric_changes: list[dict[str, str]] = field(default_factory=list)
    entity_changes: list[dict[str, str]] = field(default_factory=list)
    hedge_changes: list[dict[str, str]] = field(default_factory=list)
    similarity: float = 1.0
    mutation_types: list[str] = field(default_factory=list)
    segments: list[DiffSegment] = field(default_factory=list)

    def as_dict(self) -> MutationDiffResult:
        return {
            "numeric_changes": self.numeric_changes,
            "entity_changes": self.entity_changes,
            "hedge_changes": self.hedge_changes,
            "similarity": round(self.similarity, 4),
            "mutation_types": self.mutation_types,
            "segments": self.segments,
        }


def diff_versions(old_text: str, new_text: str) -> MutationDiffResult:
    """Diff two claim versions into a UI-renderable + analysable payload.

    Returns segments (same/changed runs with the token kinds that changed)
    plus a typed summary: NUMERIC_DRIFT, ENTITY_SUBSTITUTION, HEDGING_SHIFT,
    FRAMING_SHIFT, WORDING_DRIFT, NEAR_DUPLICATE.
    """
    old_tokens = tokenize(old_text)
    new_tokens = tokenize(new_text)

    old_nums, new_nums = _numbers(old_tokens), _numbers(new_tokens)
    old_ents, new_ents = _entities(old_tokens), _entities(new_tokens)
    old_hed, new_hed = _hedges(old_tokens), _hedges(new_tokens)

    sm = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    similarity = sm.ratio()

    summary = MutationSummary(similarity=similarity)

    summary.numeric_changes = [
        {"removed": t, "added": ""} for t in sorted(old_nums - new_nums)
    ] + [
        {"removed": "", "added": t} for t in sorted(new_nums - old_nums)
    ]
    summary.entity_changes = [
        {"removed": t, "added": ""} for t in sorted(old_ents - new_ents)
    ] + [
        {"removed": "", "added": t} for t in sorted(new_ents - old_ents)
    ]
    summary.hedge_changes = [
        {"word": t, "direction": "lost"} for t in sorted(old_hed - new_hed)
    ] + [
        {"word": t, "direction": "gained"} for t in sorted(new_hed - old_hed)
    ]

    # segments: group opcodes into same/changed runs for the UI
    segments: list[DiffSegment] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            if segments and segments[-1]["type"] == "same":
                segments[-1]["old"] = (segments[-1]["old"] + " " + " ".join(old_tokens[i1:i2])).strip()
                segments[-1]["new"] = (segments[-1]["new"] + " " + " ".join(new_tokens[j1:j2])).strip()
            else:
                segments.append({
                    "type": "same",
                    "old": " ".join(old_tokens[i1:i2]),
                    "new": " ".join(new_tokens[j1:j2]),
                    "kinds": [],
                })
        else:
            old_run = old_tokens[i1:i2]
            new_run = new_tokens[j1:j2]
            kinds: set[str] = set()
            if any(_NUMBER_RE.match(t) for t in old_run + new_run):
                kinds.add("numeric")
            if any(t.lower() in HEDGE_WORDS for t in old_run + new_run):
                kinds.add("hedge")
            if any(t in (old_ents | new_ents) and t.isalpha() and t[:1].isupper()
                   for t in old_run + new_run):
                kinds.add("entity")
            if not kinds:
                kinds.add("wording")
            segments.append({
                "type": "changed",
                "old": " ".join(old_run),
                "new": " ".join(new_run),
                "kinds": sorted(kinds),
            })

    summary.segments = segments

    # classify mutation types
    types: list[str] = []
    if summary.numeric_changes:
        types.append("NUMERIC_DRIFT")
    if summary.entity_changes:
        types.append("ENTITY_SUBSTITUTION")
    if summary.hedge_changes:
        types.append("HEDGING_SHIFT")
    if similarity < 0.65:
        types.append("FRAMING_SHIFT")
    elif similarity < 0.9:
        types.append("WORDING_DRIFT")
    elif not types:
        types.append("NEAR_DUPLICATE")
    summary.mutation_types = types

    return summary.as_dict()
