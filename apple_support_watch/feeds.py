from __future__ import annotations

import html
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import Event


def _absolute(base_url: str, relative: str | None) -> str | None:
    if not relative:
        return None
    return f"{base_url.rstrip('/')}/{relative.lstrip('/')}" if base_url else relative


def _event_html(event: Event, base_url: str) -> str:
    parts = [f"<p>{html.escape(event.description)}</p>"] if event.description else []
    if event.kind == "updated":
        parts.append(f"<p><strong>{event.added} added · {event.removed} removed</strong></p>")
        if event.diff_excerpt:
            formatted = []
            for line in event.diff_excerpt:
                color = "#087f23" if line.startswith("+") else "#b00020"
                formatted.append(f'<span style="color:{color}">{html.escape(line)}</span>')
            parts.append(f"<pre>{'<br>'.join(formatted)}</pre>")
    source_name = event.source_name or "Apple Support"
    links = [f'<a href="{html.escape(event.url, quote=True)}">{html.escape(source_name)}</a>']
    diff_url = _absolute(base_url, event.diff_page)
    if diff_url:
        links.append(f'<a href="{html.escape(diff_url, quote=True)}">Full diff</a>')
    if event.counterpart_url:
        links.append(f'<a href="{html.escape(event.counterpart_url, quote=True)}">Other language</a>')
    parts.append(f"<p>{' · '.join(links)}</p>")
    return "".join(parts)


def write_feed(path: Path, events: list[Event], title: str, base_url: str, limit: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = base_url or "https://support.apple.com/"
    ET.SubElement(channel, "description").text = f"Automated Apple Support monitoring — {title}"
    ET.SubElement(channel, "language").text = "fr-FR" if "FR" in title else "en-US"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc), usegmt=True
    )
    visible_events = [event for event in events if event.kind in {"new", "updated"}]
    for event in sorted(visible_events, key=lambda item: item.detected_at, reverse=True)[:limit]:
        item = ET.SubElement(channel, "item")
        prefix = {"new": "NEW", "updated": "UPDATED"}[event.kind]
        ET.SubElement(item, "title").text = f"[{prefix}] {event.title}"
        ET.SubElement(item, "link").text = event.url
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = event.event_id
        parsed = datetime.fromisoformat(event.detected_at.replace("Z", "+00:00"))
        ET.SubElement(item, "pubDate").text = format_datetime(parsed)
        ET.SubElement(item, "description").text = _event_html(event, base_url)
    ET.indent(rss)
    path.write_bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True))
