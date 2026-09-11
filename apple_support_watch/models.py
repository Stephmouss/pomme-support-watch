from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Source:
    locale: str
    label: str
    index: str


@dataclass
class Article:
    url: str
    article_id: str
    locale: str
    title: str
    description: str
    markdown: str
    published_date: str | None = None
    content_hash: str = ""


@dataclass
class Event:
    event_id: str
    kind: str
    locale: str
    article_id: str
    title: str
    url: str
    detected_at: str
    sitemap_lastmod: str | None = None
    published_date: str | None = None
    description: str = ""
    added: int = 0
    removed: int = 0
    diff_excerpt: list[str] = field(default_factory=list)
    diff_page: str | None = None
    counterpart_url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "locale": self.locale,
            "article_id": self.article_id,
            "title": self.title,
            "url": self.url,
            "detected_at": self.detected_at,
            "sitemap_lastmod": self.sitemap_lastmod,
            "published_date": self.published_date,
            "description": self.description,
            "added": self.added,
            "removed": self.removed,
            "diff_excerpt": self.diff_excerpt,
            "diff_page": self.diff_page,
            "counterpart_url": self.counterpart_url,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Event":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in allowed if key in value})

