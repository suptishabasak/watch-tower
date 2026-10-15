"""Text normalisation and comparison.

normalize_text() turns raw page text into stable lines (whitespace collapsed, volatile tokens such as
timestamps and relative times removed, obvious ad labels dropped). compare_text() then diffs two such
line lists into added / removed / modified changes, with word-level segments for modified lines.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

MAX_CHANGES = 200
PAIR_SIMILARITY = 0.5
PAIR_BLOCK_LIMIT = 2500  # skip pairing for huge replace-blocks to bound CPU

_WS = re.compile(r"[ \t\f\v]+")

# Masked out of a line (the rest of the line is kept, so "Posted 5 minutes ago: Big news" stays stable)
_VOLATILE = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", re.I),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s?[ap]\.?m\.?(?!\w)", re.I),
    re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"),
    re.compile(r"\b\d{1,2}:\d{2}\s?(?:UTC|GMT|[ECMP][SD]T)\b"),
    re.compile(r"\b(?:\d+|an?|a few)\s+(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\s+ago\b", re.I),
    re.compile(r"\b(?:just now|moments? ago)\b", re.I),
    re.compile(r"(?:©|\(c\)|copyright)\s*\d{4}(?:\s*[-–]\s*\d{4})?", re.I),
    re.compile(r"\b\d{10,13}\b"),  # epoch timestamps / long ids
    re.compile(r"\b[0-9a-f]{24,}\b", re.I),  # tokens, hashes
]

# Whole lines that are page chrome rather than content
_NOISE_LINE = re.compile(
    r"^(?:advertisements?|ads?|sponsored(?: content)?|promoted|ad ?choices|"
    r"skip to (?:main )?content|loading(?:\.{3}|…)?|scroll to continue)$",
    re.I,
)

_PRICE_RE = re.compile(
    r"[$€£¥₹]\s?\d|\d[\d.,]*\s?(?:[$€£¥₹]|usd|eur|gbp|inr)(?!\w)|\b(?:price|prices|pricing|sale|discount)\b",
    re.I,
)
_AVAILABILITY_TERMS = ["in stock", "out of stock", "sold out", "available", "unavailable", "waitlist", "left"]


def mask_volatile(line: str) -> str:
    for pattern in _VOLATILE:
        line = pattern.sub("", line)
    return _WS.sub(" ", line).strip()


def normalize_text(text: str) -> list[str]:
    lines: list[str] = []
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    for raw in cleaned.split("\n"):
        line = _WS.sub(" ", raw).strip()
        if not line or _NOISE_LINE.match(line):
            continue
        line = mask_volatile(line)
        if not re.search(r"\w", line):
            continue
        lines.append(line)
    return lines


def fingerprint(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def change_key(prev_hash: str, new_hash: str) -> str:
    return hashlib.sha256(f"{prev_hash}:{new_hash}".encode()).hexdigest()


@dataclass
class FocusMatcher:
    terms: list[str]
    price: bool

    @classmethod
    def parse(cls, focus: str | None) -> "FocusMatcher | None":
        if not focus or not focus.strip():
            return None
        terms: list[str] = []
        price = False
        for raw in re.split(r"[,;\n]", focus):
            t = raw.strip().lower()
            if not t:
                continue
            if t in {"price", "prices", "pricing", "cost", "costs"}:
                price = True
            elif t == "availability":
                terms.extend(_AVAILABILITY_TERMS)
            else:
                terms.extend([part for part in t.split() if part])
        if not terms and not price:
            return None
        return cls(terms, price)

    def matches(self, text: str | None) -> bool:
        if not text:
            return False
        if self.price and _PRICE_RE.search(text):
            return True
        low = text.lower()
        return any(t in low for t in self.terms)


@dataclass
class Change:
    kind: str  # added | removed | modified
    before: str | None = None
    after: str | None = None
    segments: list[dict] | None = None
    relevant: bool = True


@dataclass
class DiffResult:
    changes: list[Change]
    counts: dict  # relevant changes only
    ignored: int = 0  # changes outside the monitor's focus
    omitted: int = 0  # changes dropped to cap storage

    @property
    def has_changes(self) -> bool:
        return bool(self.changes) or self.omitted > 0

    @property
    def significant(self) -> bool:
        return sum(self.counts.values()) > 0


def word_segments(before: str, after: str) -> list[dict]:
    a = re.findall(r"\s+|\S+", before)
    b = re.findall(r"\s+|\S+", after)
    segments: list[dict] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            segments.append({"type": "equal", "text": "".join(a[i1:i2])})
            continue
        if i2 > i1:
            segments.append({"type": "del", "text": "".join(a[i1:i2])})
        if j2 > j1:
            segments.append({"type": "add", "text": "".join(b[j1:j2])})
    return segments


def _resolve_block(old_block: list[str], new_block: list[str]) -> list[Change]:
    """Within a replaced region, pair similar lines as 'modified'; leftovers are removed / added."""
    pairs: dict[int, int] = {}
    if len(old_block) * len(new_block) <= PAIR_BLOCK_LIMIT:
        used: set[int] = set()
        for oi, old_line in enumerate(old_block):
            best_j, best_r = None, 0.0
            for nj, new_line in enumerate(new_block):
                if nj in used:
                    continue
                sm = SequenceMatcher(None, old_line, new_line, autojunk=False)
                if sm.real_quick_ratio() <= best_r or sm.quick_ratio() <= best_r:
                    continue
                r = sm.ratio()
                if r > best_r:
                    best_j, best_r = nj, r
            if best_j is not None and best_r >= PAIR_SIMILARITY:
                pairs[oi] = best_j
                used.add(best_j)

    changes: list[Change] = []
    for oi, old_line in enumerate(old_block):
        if oi in pairs:
            new_line = new_block[pairs[oi]]
            changes.append(Change("modified", old_line, new_line, word_segments(old_line, new_line)))
        else:
            changes.append(Change("removed", before=old_line))
    paired_new = set(pairs.values())
    for nj, new_line in enumerate(new_block):
        if nj not in paired_new:
            changes.append(Change("added", after=new_line))
    return changes


def compare_text(old: list[str], new: list[str], focus: str | None = None) -> DiffResult:
    changes: list[Change] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            changes.extend(Change("removed", before=line) for line in old[i1:i2])
        elif tag == "insert":
            changes.extend(Change("added", after=line) for line in new[j1:j2])
        else:
            changes.extend(_resolve_block(old[i1:i2], new[j1:j2]))

    matcher = FocusMatcher.parse(focus)
    if matcher:
        for c in changes:
            c.relevant = matcher.matches(c.before) or matcher.matches(c.after)
        changes.sort(key=lambda c: not c.relevant)  # stable: relevant first

    counts = {"added": 0, "removed": 0, "modified": 0}
    ignored = 0
    for c in changes:
        if c.relevant:
            counts[c.kind] += 1
        else:
            ignored += 1

    omitted = max(0, len(changes) - MAX_CHANGES)
    return DiffResult(changes=changes[:MAX_CHANGES], counts=counts, ignored=ignored, omitted=omitted)


def _trunc(text: str | None, limit: int = 100) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _highlight(c: Change) -> str:
    if c.kind == "modified":
        return f"~ “{_trunc(c.before)}” → “{_trunc(c.after)}”"
    if c.kind == "added":
        return f"+ {_trunc(c.after)}"
    return f"- {_trunc(c.before)}"


def relevant_changes(result: DiffResult) -> list[Change]:
    order = {"modified": 0, "added": 1, "removed": 2}
    return sorted((c for c in result.changes if c.relevant), key=lambda c: order[c.kind])


def summarize(result: DiffResult, max_items: int = 3) -> str:
    c = result.counts
    parts = [f"{c[k]} {k}" for k in ("added", "modified", "removed") if c[k]]
    lines = [", ".join(parts) or "No visible changes"]
    shown = relevant_changes(result)[:max_items]
    lines.extend(_highlight(ch) for ch in shown)
    rest = sum(c.values()) - len(shown)
    if rest > 0:
        lines.append(f"…and {rest} more")
    return "\n".join(lines)


def serialize_diff(result: DiffResult) -> str:
    items = [
        {"kind": c.kind, "before": c.before, "after": c.after, "segments": c.segments, "relevant": c.relevant}
        for c in result.changes
    ]
    return json.dumps({"items": items, "omitted": result.omitted})