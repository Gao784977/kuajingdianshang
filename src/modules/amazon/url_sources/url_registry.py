"""URL registry — append-only list of URLs the user explicitly provided.

The fetcher refuses any URL not in this registry, enforcing the spec
rule "禁止访问未由用户提供的 URL". Construction is from the
``urls`` array in the user input JSON.

The registry does not deduplicate — if the user lists the same URL
twice (perhaps under different keywords), both entries are kept so
downstream code can correlate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from .url_classifier import UrlClassification, classify_url


@dataclass
class UrlEntry:
    """One registered URL.

    Attributes:
        source_url: The exact string the user provided.
        kind: Result of :func:`classify_url`.
        provided_by: Where the URL came from — typically the JSON
            key name (``"urls"``) or a sub-key (``"product_candidates"``).
        notes: Free-text context the user attached, if any.
        classification: The full :class:`UrlClassification` (cached
            at registration time so downstream code does not need to
            re-classify).
    """

    source_url: str
    kind: str
    provided_by: str
    notes: str = ""
    classification: Optional[UrlClassification] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "kind": self.kind,
            "provided_by": self.provided_by,
            "notes": self.notes,
            "classification": (
                self.classification.to_dict() if self.classification else None
            ),
        }


@dataclass
class UrlRegistry:
    """Append-only registry of user-supplied URLs.

    The registry is the single source of truth for "is this URL
    user-provided?" — the fetcher refuses anything not registered.
    """

    entries: List[UrlEntry] = field(default_factory=list)

    def register(
        self,
        url: str,
        *,
        provided_by: str = "user_input",
        notes: str = "",
    ) -> UrlEntry:
        """Add ``url`` to the registry and return the new entry.

        Re-registering the same URL produces a second entry (no
        dedup) so that callers can correlate a URL with multiple
        contexts (e.g. one listing under ``urls`` and again under
        ``product_candidates``).
        """
        classification = classify_url(url)
        entry = UrlEntry(
            source_url=url,
            kind=classification.kind,
            provided_by=provided_by,
            notes=notes,
            classification=classification,
        )
        self.entries.append(entry)
        return entry

    def register_many(
        self,
        urls: List[str],
        *,
        provided_by: str = "user_input",
    ) -> List[UrlEntry]:
        """Convenience bulk-register. Returns the new entries."""
        return [self.register(u, provided_by=provided_by) for u in urls]

    def contains(self, url: str) -> bool:
        """True when ``url`` has been registered (exact string match)."""
        return any(e.source_url == url for e in self.entries)

    def __iter__(self) -> Iterator[UrlEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def to_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.entries]


def registry_from_input(user_input: Dict[str, Any]) -> UrlRegistry:
    """Build a :class:`UrlRegistry` from a user input JSON dict.

    Recognises these top-level keys:

    * ``urls``                — list of {"url": "...", "notes": "..."}
    * ``product_candidates``  — list of {"url": "...", ...}
    * ``supplier_information``— list of {"url": "...", ...}

    Each URL is registered with ``provided_by`` set to the key name
    so downstream code can correlate provenance.
    """
    registry = UrlRegistry()
    for key in ("urls", "product_candidates", "supplier_information"):
        items = user_input.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                url = item.get("url") or item.get("source_url")
                notes = item.get("notes") or ""
            else:
                url = str(item)
                notes = ""
            if url:
                registry.register(str(url), provided_by=key, notes=notes)
    return registry


__all__ = ["UrlEntry", "UrlRegistry", "registry_from_input"]
