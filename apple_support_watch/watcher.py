from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .diffing import unified_changes, write_html_diff
from .extract import article_id_from_url, extract_article
from .feeds import write_feed
from .http import HttpClient
from .models import Event, Source
from .site import write_index
from .sitemaps import fetch_articles


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class Watcher:
    def __init__(self, root: Path, config: dict[str, Any], dry_run: bool = False) -> None:
        self.root = root
        self.config = config
        self.dry_run = dry_run
        self.state_dir = root / "state"
        self.snapshot_dir = root / "snapshots"
        self.event_dir = root / "events"
        self.public_dir = root / "public"
        self.site_url = os.getenv("SITE_URL", "").rstrip("/")
        self.client = HttpClient(
            config["user_agent"], config["request_timeout_seconds"], config["request_delay_seconds"]
        )
        self.created_events: list[Event] = []

    def _state_path(self, locale: str) -> Path:
        return self.state_dir / f"{locale}.json"

    def _snapshot_path(self, locale: str, article_id: str) -> Path:
        return self.snapshot_dir / locale / f"{article_id}.md"

    def _events_path(self, locale: str) -> Path:
        return self.event_dir / f"{locale}.json"

    def _load_events(self, locale: str) -> list[Event]:
        return [Event.from_dict(item) for item in load_json(self._events_path(locale), [])]

    def _save_events(self, locale: str, events: list[Event]) -> None:
        save_json(self._events_path(locale), [event.as_dict() for event in events[:1000]])

    def _fetch_article(self, url: str, locale: str):
        return extract_article(self.client.get_text(url), url, locale)

    def _event_id(self, kind: str, locale: str, article_id: str, marker: str) -> str:
        digest = hashlib.sha256(f"{kind}|{locale}|{article_id}|{marker}".encode()).hexdigest()[:16]
        return f"apple-support-watch:{locale}:{article_id}:{kind}:{digest}"

    def _counterpart(self, states: dict[str, dict], locale: str, article_id: str) -> str | None:
        other = "fr-fr" if locale == "en-us" else "en-us"
        for url, record in states.get(other, {}).get("articles", {}).items():
            if record.get("article_id") == article_id and record.get("active", True):
                return url
        return None

    def _record_new(self, source: Source, record: dict, lastmod: str | None, timestamp: str) -> Event | None:
        try:
            article = self._fetch_article(record["url"], source.locale)
        except Exception as exc:
            record["last_error"] = str(exc)
            return None
        snapshot = self._snapshot_path(source.locale, article.article_id)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not self.dry_run:
            snapshot.write_text(article.markdown, encoding="utf-8")
        record.update(
            {
                "article_id": article.article_id,
                "title": article.title,
                "description": article.description,
                "hash": article.content_hash,
                "baselined": True,
                "last_checked": timestamp,
                "published_date": article.published_date,
                "last_error": None,
                "new_pending": False,
            }
        )
        return Event(
            event_id=self._event_id("new", source.locale, article.article_id, article.content_hash),
            kind="new",
            locale=source.locale,
            article_id=article.article_id,
            title=article.title,
            url=article.url,
            detected_at=timestamp,
            sitemap_lastmod=lastmod,
            published_date=article.published_date,
            description=article.description,
        )

    def _check_content(self, source: Source, record: dict, timestamp: str, emit: bool = True) -> Event | None:
        try:
            article = self._fetch_article(record["url"], source.locale)
        except Exception as exc:
            record["last_error"] = str(exc)
            return None
        snapshot = self._snapshot_path(source.locale, article.article_id)
        old = snapshot.read_text(encoding="utf-8") if snapshot.exists() else ""
        old_hash = record.get("hash")
        changed = bool(old and old_hash and article.content_hash != old_hash)
        record.update(
            {
                "article_id": article.article_id,
                "title": article.title,
                "description": article.description,
                "hash": article.content_hash,
                "baselined": True,
                "last_checked": timestamp,
                "published_date": article.published_date,
                "last_error": None,
            }
        )
        if not self.dry_run:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_text(article.markdown, encoding="utf-8")
        if not changed or not emit:
            return None
        excerpt, added, removed = unified_changes(
            old, article.markdown, int(self.config["feed_diff_line_limit"])
        )
        stamp = timestamp.replace(":", "-")
        relative = f"diffs/{source.locale}/{article.article_id}/{stamp}.html"
        if not self.dry_run:
            write_html_diff(self.public_dir / relative, old, article.markdown, article.title, article.url)
        return Event(
            event_id=self._event_id("updated", source.locale, article.article_id, article.content_hash),
            kind="updated",
            locale=source.locale,
            article_id=article.article_id,
            title=article.title,
            url=article.url,
            detected_at=timestamp,
            sitemap_lastmod=record.get("sitemap_lastmod"),
            published_date=article.published_date,
            description=article.description,
            added=added,
            removed=removed,
            diff_excerpt=excerpt,
            diff_page=relative,
        )

    def run(self) -> dict[str, Any]:
        timestamp = now_iso()
        sources = [Source(**item) for item in self.config["sources"]]
        states = {source.locale: load_json(self._state_path(source.locale), {}) for source in sources}
        fetched_maps: dict[str, dict[str, str | None]] = {}

        for source in sources:
            fetched_maps[source.locale] = fetch_articles(self.client, source.index, source.locale)

        for source in sources:
            current = fetched_maps[source.locale]
            state = states[source.locale]
            initial = not bool(state.get("initialized"))
            previous_count = int(state.get("sitemap_count", 0))
            if previous_count and len(current) < previous_count * 0.8:
                raise ValueError(
                    f"Refusing unusually large sitemap shrink for {source.locale}: "
                    f"{previous_count} to {len(current)}"
                )
            records = state.setdefault("articles", {})
            events = self._load_events(source.locale)

            if initial:
                for url, lastmod in current.items():
                    records[url] = {
                        "url": url,
                        "article_id": article_id_from_url(url),
                        "sitemap_lastmod": lastmod,
                        "first_seen": timestamp,
                        "active": True,
                        "missing_count": 0,
                        "baselined": False,
                        "new_pending": False,
                    }
                state["initialized"] = timestamp
            else:
                for url, lastmod in current.items():
                    if url not in records:
                        record = {
                            "url": url,
                            "article_id": article_id_from_url(url),
                            "sitemap_lastmod": lastmod,
                            "first_seen": timestamp,
                            "active": True,
                            "missing_count": 0,
                            "baselined": False,
                            "new_pending": True,
                        }
                        records[url] = record
                        event = self._record_new(source, record, lastmod, timestamp)
                        if event:
                            events.insert(0, event)
                            self.created_events.append(event)
                    else:
                        record = records[url]
                        prior_lastmod = record.get("sitemap_lastmod")
                        record["active"] = True
                        record["missing_count"] = 0
                        record["sitemap_lastmod"] = lastmod
                        if record.get("new_pending"):
                            event = self._record_new(source, record, lastmod, timestamp)
                            if event:
                                events.insert(0, event)
                                self.created_events.append(event)
                        elif lastmod != prior_lastmod:
                            event = self._check_content(source, record, timestamp, emit=True)
                            if event:
                                events.insert(0, event)
                                self.created_events.append(event)

                confirmations = int(self.config["removal_confirmations"])
                for url, record in records.items():
                    if url in current or not record.get("active", True):
                        continue
                    record["missing_count"] = int(record.get("missing_count", 0)) + 1
                    if record["missing_count"] >= confirmations:
                        record["active"] = False
                        marker = f"removed:{timestamp}"
                        event = Event(
                            event_id=self._event_id("removed", source.locale, record["article_id"], marker),
                            kind="removed",
                            locale=source.locale,
                            article_id=record["article_id"],
                            title=record.get("title", record["article_id"]),
                            url=url,
                            detected_at=timestamp,
                            sitemap_lastmod=record.get("sitemap_lastmod"),
                            description="The URL disappeared from the Apple Support sitemap in two consecutive checks.",
                        )
                        events.insert(0, event)
                        self.created_events.append(event)

            # Build initial snapshots progressively, newest sitemap dates first.
            pending = [
                record
                for record in records.values()
                if record.get("active", True)
                and not record.get("baselined")
                and not record.get("new_pending")
            ]
            pending.sort(key=lambda item: item.get("sitemap_lastmod") or "", reverse=True)
            for record in pending[: int(self.config["bootstrap_batch_size"])]:
                self._check_content(source, record, timestamp, emit=False)

            # Rotate a small content audit independently of sitemap lastmod.
            audited = [
                record
                for record in records.values()
                if record.get("active", True)
                and record.get("baselined")
                and record.get("last_checked") != timestamp
            ]
            audited.sort(key=lambda item: item.get("last_checked") or "")
            for record in audited[: int(self.config["audit_batch_size"])]:
                event = self._check_content(source, record, timestamp, emit=not initial)
                if event:
                    events.insert(0, event)
                    self.created_events.append(event)

            state["last_success"] = timestamp
            state["sitemap_count"] = len(current)
            if not self.dry_run:
                save_json(self._state_path(source.locale), state)
                self._save_events(source.locale, events)

        # Add cross-language links after both states are current.
        for locale in states:
            events = self._load_events(locale) if not self.dry_run else []
            for event in events:
                event.counterpart_url = self._counterpart(states, locale, event.article_id)
            if not self.dry_run:
                self._save_events(locale, events)

        status = {"last_success": timestamp, "sources": {}}
        for source in sources:
            records = states[source.locale].get("articles", {})
            status["sources"][source.locale] = {
                "active": sum(1 for record in records.values() if record.get("active", True)),
                "baselined": sum(1 for record in records.values() if record.get("baselined")),
                "pending": sum(1 for record in records.values() if record.get("active", True) and not record.get("baselined")),
            }
            if not self.dry_run:
                events = self._load_events(source.locale)
                new_events = [event for event in events if event.kind == "new"]
                updated_events = [event for event in events if event.kind in {"updated", "removed"}]
                label = "FR" if source.locale == "fr-fr" else "EN"
                write_feed(
                    self.public_dir / "feeds" / f"{source.locale}-new.xml",
                    new_events,
                    f"Apple Support {label} — New articles",
                    self.site_url,
                    int(self.config["feed_item_limit"]),
                )
                write_feed(
                    self.public_dir / "feeds" / f"{source.locale}-updated.xml",
                    updated_events,
                    f"Apple Support {label} — Updated articles",
                    self.site_url,
                    int(self.config["feed_item_limit"]),
                )
        if not self.dry_run:
            write_index(self.public_dir, status, self.config["site_title"])
        return status
