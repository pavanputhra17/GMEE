"""Deterministic English text-change heuristics, not a transmission detector.

Spans are half-open Python character offsets into the original input strings.
Only lexical changes count as meaningful; whitespace, case and standalone
punctuation changes cannot by themselves establish a mutation parent.
"""

import difflib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypedDict

ALGORITHM_VERSION = "gmee-typed-text-v1"

_NUMBER_PATTERN = r"[+−-]?(?:[$€£]\s*)?\d+(?:[.,]\d+)*(?:\s?%|[kmbKMB]\b)?"
_NUMBER_RE = re.compile(rf"^{_NUMBER_PATTERN}$")
_TOKEN_RE = re.compile(
    rf"{_NUMBER_PATTERN}|[^\W\d_]+(?:['’][^\W\d_]+)*|\w+|[^\w\s]",
    re.UNICODE,
)

HEDGE_WORDS = frozenset(
    {
        "allegedly",
        "reportedly",
        "unverified",
        "claimed",
        "claims",
        "rumored",
        "rumoured",
        "rumour",
        "rumor",
        "purportedly",
        "seemingly",
        "apparently",
        "may",
        "might",
        "could",
        "possibly",
        "perhaps",
        "sources",
        "according",
        "believed",
        "suspected",
        "speculation",
        "unconfirmed",
        "likely",
        "unlikely",
        "probably",
        "potentially",
        "estimated",
    }
)
POLARITY_WORDS = frozenset(
    {
        "not",
        "no",
        "never",
        "neither",
        "nor",
        "without",
        "deny",
        "denies",
        "denied",
        "false",
        "untrue",
        "cannot",
        "can't",
        "won't",
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        "doesn't",
        "didn't",
        "don't",
        "hasn't",
        "haven't",
        "hadn't",
        "couldn't",
        "wouldn't",
        "shouldn't",
        "mustn't",
    }
)
ATTRIBUTION_WORDS = frozenset(
    {
        "according",
        "sources",
        "source",
        "said",
        "says",
        "say",
        "stated",
        "states",
        "reported",
        "reports",
        "report",
        "claimed",
        "claims",
        "announced",
        "announces",
        "cited",
        "cites",
        "told",
        "spokesperson",
    }
)
SCOPE_WORDS = frozenset(
    {
        "all",
        "every",
        "everyone",
        "everything",
        "any",
        "some",
        "many",
        "most",
        "few",
        "several",
        "none",
        "only",
        "each",
        "both",
        "entire",
        "always",
        "sometimes",
        "often",
        "everywhere",
        "nationwide",
        "worldwide",
        "globally",
        "locally",
        "approximately",
        "about",
        "nearly",
        "at least",
        "at most",
        "more than",
        "less than",
        "up to",
        "over",
        "under",
    }
)
_SCOPE_PHRASES = ("at least", "at most", "more than", "less than", "up to")
_STOPWORDS = (
    frozenset(
        {
            "the",
            "a",
            "an",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "and",
            "or",
            "is",
            "are",
            "was",
            "were",
            "it",
            "its",
            "as",
            "by",
            "with",
            "from",
            "that",
            "this",
            "has",
            "have",
            "had",
            "but",
            "will",
            "after",
            "before",
            "into",
            "than",
            "then",
            "new",
            "first",
            "officials",
            "president",
        }
    )
    | HEDGE_WORDS
    | POLARITY_WORDS
    | ATTRIBUTION_WORDS
    | SCOPE_WORDS
)

LIMITATIONS = (
    "English lexical heuristics only; no semantic entailment, fact checking, or model inference.",
    "Capitalized words are entity proxies, not named-entity recognition; sentence starts, aliases and uncased names can be misclassified.",
    "Numbers are surface forms, not unit-aware quantities; equivalent formats or units may be flagged.",
    "Polarity, hedge, attribution and scope lexicons do not resolve negation scope, quotation, sarcasm or coreference.",
    "Case, whitespace and standalone punctuation are ignored for meaningful-change classification; this can miss punctuation-only meaning changes.",
    "Lexical differences and timestamps do not prove copying, causal lineage or observed propagation.",
    "Naive timestamps are interpreted as UTC; missing or equal timestamps cannot establish temporal precedence.",
)

ChangeKind = Literal[
    "numeric", "entity", "polarity", "hedge", "attribution", "scope", "wording"
]
_KIND_TYPES: dict[ChangeKind, str] = {
    "numeric": "NUMERIC_DRIFT",
    "entity": "ENTITY_SUBSTITUTION",
    "polarity": "POLARITY_SHIFT",
    "hedge": "HEDGING_SHIFT",
    "attribution": "ATTRIBUTION_SHIFT",
    "scope": "SCOPE_SHIFT",
    "wording": "WORDING_DRIFT",
}
_TYPED_KINDS: tuple[ChangeKind, ...] = (
    "numeric",
    "entity",
    "polarity",
    "hedge",
    "attribution",
    "scope",
)


@dataclass(frozen=True)
class TextToken:
    text: str
    start: int
    end: int

    @property
    def normalized(self) -> str:
        return re.sub(
            r"\s+", "", self.text.casefold().replace("’", "'").replace("−", "-")
        )

    @property
    def lexical(self) -> bool:
        return any(c.isalnum() for c in self.text)


class TextSpan(TypedDict):
    start: int
    end: int
    text: str


class ChangedSpan(TypedDict):
    operation: str
    older_span: TextSpan
    newer_span: TextSpan
    kinds: list[ChangeKind]


class ChangeDetail(ChangedSpan):
    kind: ChangeKind
    mutation_type: str
    removed: list[str]
    added: list[str]
    direction: str


class MutationAnalysis(TypedDict):
    algorithm_version: str
    mutation_types: list[str]
    changes: list[ChangeDetail]
    changed_spans: list[ChangedSpan]
    similarity: float
    meaningful_change: bool
    observed_propagation: bool
    inference: str
    text_basis: str
    span_offset_unit: str
    older_timestamp: str | None
    newer_timestamp: str | None
    temporal_order: str
    lag_seconds: float | None
    limitations: list[str]


def tokens_with_spans(text: str) -> list[TextToken]:
    return [TextToken(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def tokenize(text: str) -> list[str]:
    return [t.text for t in tokens_with_spans(text or "")]


def utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _span(text: str, tokens: list[TextToken], start: int, end: int) -> TextSpan:
    if start == end:
        offset = tokens[start].start if start < len(tokens) else len(text)
        return {"start": offset, "end": offset, "text": ""}
    lo, hi = tokens[start].start, tokens[end - 1].end
    return {"start": lo, "end": hi, "text": text[lo:hi]}


def _entity(token: TextToken) -> bool:
    return (
        token.text.isalpha()
        and token.text[:1].isupper()
        and (len(token.text) > 2 or (len(token.text) > 1 and token.text.isupper()))
        and token.normalized not in _STOPWORDS
    )


def _features(tokens: list[TextToken], kind: ChangeKind) -> list[str]:
    if kind == "numeric":
        return [t.normalized for t in tokens if _NUMBER_RE.fullmatch(t.text)]
    if kind == "entity":
        return [t.text for t in tokens if _entity(t)]
    lexicons = {
        "polarity": POLARITY_WORDS,
        "hedge": HEDGE_WORDS,
        "attribution": ATTRIBUTION_WORDS,
        "scope": SCOPE_WORDS,
    }
    if kind == "wording":
        return [t.normalized for t in tokens]
    words = [t.normalized for t in tokens]
    found = [w for w in words if w in lexicons[kind]]
    if kind == "scope":
        found.extend(
            phrase
            for phrase in _SCOPE_PHRASES
            if any(words[i : i + 2] == phrase.split() for i in range(len(words) - 1))
        )
    return found


def _touches_attribution(tokens: list[TextToken], start: int, end: int) -> bool:
    # Include the source next to a reporting cue, so "Alice said" -> "Bob said"
    # changes attribution even when the reporting verb itself is unchanged.
    context = tokens[max(0, start - 4) : min(len(tokens), end + 4)]
    return any(t.normalized in ATTRIBUTION_WORDS for t in context)


def analyze_text_change(
    older_text: str,
    newer_text: str,
    *,
    older_timestamp: datetime | None = None,
    newer_timestamp: datetime | None = None,
) -> MutationAnalysis:
    old = [t for t in tokens_with_spans(older_text) if t.lexical]
    new = [t for t in tokens_with_spans(newer_text) if t.lexical]
    matcher = difflib.SequenceMatcher(
        a=[t.normalized for t in old],
        b=[t.normalized for t in new],
        autojunk=False,
    )
    changed_spans: list[ChangedSpan] = []
    changes: list[ChangeDetail] = []
    found_kinds: set[ChangeKind] = set()
    for operation, i1, i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            continue
        older_span, newer_span = (
            _span(older_text, old, i1, i2),
            _span(newer_text, new, j1, j2),
        )
        old_run, new_run = old[i1:i2], new[j1:j2]
        kinds: list[ChangeKind] = []
        for kind in _TYPED_KINDS:
            removed, added = _features(old_run, kind), _features(new_run, kind)
            attribution_source = (
                kind == "attribution"
                and (
                    _touches_attribution(old, i1, i2)
                    or _touches_attribution(new, j1, j2)
                )
                and any(_entity(t) for t in old_run + new_run)
            )
            # Scope phrases may straddle an opcode boundary ("at least" ->
            # "at most"); retain the complete phrase's context for detection.
            if kind == "scope":
                old_scope = _features(old[max(0, i1 - 1) : min(len(old), i2 + 1)], kind)
                new_scope = _features(new[max(0, j1 - 1) : min(len(new), j2 + 1)], kind)
                if old_scope != new_scope:
                    removed, added = old_scope, new_scope
            if attribution_source and removed == added:
                removed = [t.normalized for t in old_run if _entity(t)]
                added = [t.normalized for t in new_run if _entity(t)]
            if removed == added:
                continue
            kinds.append(kind)
            found_kinds.add(kind)
            changes.append(
                {
                    "operation": operation,
                    "older_span": older_span,
                    "newer_span": newer_span,
                    "kinds": [kind],
                    "kind": kind,
                    "mutation_type": _KIND_TYPES[kind],
                    "removed": removed,
                    "added": added,
                    "direction": "shifted"
                    if removed and added
                    else "lost"
                    if removed
                    else "gained",
                }
            )
        if not kinds:
            kinds = ["wording"]
            changes.append(
                {
                    "operation": operation,
                    "older_span": older_span,
                    "newer_span": newer_span,
                    "kinds": kinds,
                    "kind": "wording",
                    "mutation_type": "WORDING_DRIFT",
                    "removed": _features(old_run, "wording"),
                    "added": _features(new_run, "wording"),
                    "direction": "shifted"
                    if old_run and new_run
                    else "lost"
                    if old_run
                    else "gained",
                }
            )
        changed_spans.append(
            {
                "operation": operation,
                "older_span": older_span,
                "newer_span": newer_span,
                "kinds": kinds,
            }
        )

    similarity = matcher.ratio()
    meaningful = bool(changed_spans)
    types = [_KIND_TYPES[k] for k in _TYPED_KINDS if k in found_kinds]
    if not meaningful:
        types = ["NEAR_DUPLICATE"]
    elif similarity < 0.65:
        types.append("FRAMING_SHIFT")
    elif similarity < 0.9 or not types:
        types.append("WORDING_DRIFT")

    older_at, newer_at = utc_timestamp(older_timestamp), utc_timestamp(newer_timestamp)
    lag = (
        (newer_at - older_at).total_seconds()
        if older_at is not None and newer_at is not None
        else None
    )
    temporal_order = (
        "unknown"
        if lag is None
        else "strictly_older"
        if lag > 0
        else "equal"
        if lag == 0
        else "reversed"
    )
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "mutation_types": types,
        "changes": changes,
        "changed_spans": changed_spans,
        "similarity": round(similarity, 4),
        "meaningful_change": meaningful,
        "observed_propagation": False,
        "inference": "inferred_text_change",
        "text_basis": "original_input_character_offsets",
        "span_offset_unit": "unicode_code_points",
        "older_timestamp": older_at.isoformat() if older_at is not None else None,
        "newer_timestamp": newer_at.isoformat() if newer_at is not None else None,
        "temporal_order": temporal_order,
        "lag_seconds": lag,
        "limitations": list(LIMITATIONS),
    }
