from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from .diffing import unified_changes, write_html_diff
from .extract import _to_markdown
from .feeds import write_feed
from .http import HttpClient
from .models import Event


REGULATORY_BASE = "https://regulatoryinfo.apple.com"
REGULATORY_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "Locale": "en",
    "Java_Locale": '"en-US"',
    "accept-language": "en",
    "X-Skip-Interceptor": "ext",
}

# Each public subsection currently advertised by Apple's module inventory is
# represented here. The module inventory itself is also watched so that a new
# Apple subsection cannot appear unnoticed.
REGULATORY_COLLECTIONS = {
    "modules/allActive": "Catalogue sections",
    "device/regulatory_data": "Environmental characteristics",
    "energyLabels": "Energy labels",
    "regulations": "Environmental regulations",
    "repairAbilityIndex": "Repairability index",
    "reach": "REACH",
    "chinaRoHs": "China RoHS",
    "batteryManagementRegulations": "Battery regulations",
    "shippingbox": "Shipping boxes",
    "device/rfexposure": "RF exposure",
    "compliance/declaration": "Declarations of conformity",
    "psti": "UK PSTI cyber security",
    "australian-cyber-security": "Australian cyber security",
    "ifu/irnf": "Irregular rhythm notifications",
    "ifu/ecg": "ECG instructions for use",
    "ifu/afib": "AFib history instructions for use",
    "ifu/cycletracking": "Cycle tracking instructions for use",
    "ifu/sanf": "Sleep apnea notifications",
    "ifu/ht": "Hearing test instructions for use",
    "ifu/haf": "Hearing aid feature instructions for use",
    "ifu/dpf": "Digital pregnancy feature instructions for use",
    "ifu/htnf": "Hypertension notifications",
    "ifu/medicalimaging": "Medical imaging",
    "ifu/rri": "Regulatory registration information",
    "vpat": "Accessibility VPAT",
    "accessibility/faq": "Accessibility FAQ",
    "accessibility/services": "Accessibility services",
    "hp": "Hearing protection",
    "euDataAct": "EU Data Act",
    "commonCharger": "Common charger",
    "batteryManagement": "Battery management",
    "eLabels": "Electronic regulatory labels",
}

VOLATILE_KEYS = {
    "addFlag",
    "deleteFlag",
    "editFlag",
    "inProgress",
    "status",
    "workflowId",
}


@dataclass
class ThemeItem:
    item_id: str
    collection: str
    title: str
    url: str
    source_name: str
    category: str
    description: str
    markdown: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.markdown.encode("utf-8")).hexdigest()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable(value: Any) -> Any:
    """Remove workflow noise and sort arrays so Apple API order does not create alerts."""
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key in VOLATILE_KEYS:
                continue
            if key == "productCategory" and isinstance(child, dict):
                result[key] = {name: child[name] for name in ("id", "name") if name in child}
            else:
                result[key] = _stable(child)
        return result
    if isinstance(value, list):
        children = [_stable(child) for child in value]
        return sorted(children, key=lambda child: json.dumps(child, ensure_ascii=False, sort_keys=True))
    return value


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return [payload["data"]]
    if isinstance(payload, dict) and payload:
        return [payload]
    return []


def _raw_id(record: dict[str, Any]) -> str:
    for key in ("id", "deviceId", "refId", "regulatoryDataId", "fileId", "module", "modelName"):
        value = record.get(key)
        if value:
            return str(value)
    return hashlib.sha256(json.dumps(_stable(record), sort_keys=True).encode()).hexdigest()[:20]


def _record_title(record: dict[str, Any], category: str) -> str:
    for key in ("productName", "serviceName", "title", "originalFileName", "fileName", "language", "module"):
        if record.get(key):
            return _clean(str(record[key]))
    model = record.get("modelName") or record.get("modelNames")
    if model:
        return f"{category} — {model if isinstance(model, str) else ', '.join(model)}"
    return category


def _regulatory_url(endpoint: str, record: dict[str, Any]) -> str:
    if endpoint == "device/rfexposure" and record.get("modelNames"):
        return f"{REGULATORY_BASE}/rfexposure/model/{record['modelNames'][0]}/en"
    routes = {
        "compliance/declaration": "eurocompliance",
        "psti": "cyber",
        "australian-cyber-security": "cyber",
        "vpat": "accessibility",
        "accessibility/faq": "accessibility",
        "accessibility/services": "accessibility",
        "hp": "hearingprotection",
        "euDataAct": "eudataact",
        "commonCharger": "commoncharger",
    }
    if endpoint.startswith("ifu/"):
        return f"{REGULATORY_BASE}/ifu"
    return f"{REGULATORY_BASE}/{routes.get(endpoint, 'regulatorydata')}"


def _regulatory_item(endpoint: str, category: str, record: dict[str, Any]) -> ThemeItem:
    stable = _stable(record)
    title = _record_title(record, category)
    models = record.get("modelNames") or record.get("modelName") or []
    if isinstance(models, str):
        models = [models]
    details = [category]
    if models:
        details.append("Models: " + ", ".join(str(model) for model in models))
    if record.get("yearOfRelease"):
        details.append("Release year: " + str(record["yearOfRelease"]))
    markdown = f"# {title}\n\nCategory: {category}\n\n```json\n{json.dumps(stable, ensure_ascii=False, indent=2, sort_keys=True)}\n```\n"
    return ThemeItem(
        item_id=f"regulatory:{endpoint}:{_raw_id(record)}",
        collection=f"regulatory:{endpoint}",
        title=title,
        url=_regulatory_url(endpoint, record),
        source_name="Apple Regulatory Information",
        category=category,
        description=" · ".join(details),
        markdown=markdown,
    )


def extract_esim_france(html: str, url: str) -> ThemeItem:
    soup = BeautifulSoup(html, "html.parser")
    option = soup.select_one('option[name="france"]') or soup.select_one("option[selected]")
    token = option.get("value") if option else None
    if not token:
        raise ValueError("France selector not found on the eSIM carrier page")
    container = soup.new_tag("div")
    for node in soup.select(f".{token}"):
        if isinstance(node, Tag) and not node.find_parent(class_=token):
            container.append(BeautifulSoup(str(node), "html.parser").find())
    body = _to_markdown(container, url)
    if len(body) < 40:
        raise ValueError("France eSIM content is unexpectedly short")
    title = "eSIM carriers and services in France"
    return ThemeItem(
        item_id="services:esim-france",
        collection="services:esim-france",
        title=title,
        url=url,
        source_name="Apple Support",
        category="Carrier & eSIM",
        description="Apple's list of French carriers and supported eSIM activation methods.",
        markdown=f"# {title}\n\n{body}",
    )


def extract_maps_france(html: str, url: str) -> ThemeItem:
    soup = BeautifulSoup(html, "html.parser")
    selector = soup.select_one("section.select-country")
    container = selector.find_next_sibling("section") if selector else None
    if container is None:
        container = soup.select_one("#driving-locations") or soup.select_one("main")
    if container is None:
        raise ValueError("France Apple Maps collection table not found")
    body = _to_markdown(container, url)
    if len(body) < 60:
        raise ValueError("France Apple Maps collection content is unexpectedly short")
    title = "Apple Maps image collection in France"
    return ThemeItem(
        item_id="services:maps-france",
        collection="services:maps-france",
        title=title,
        url=url,
        source_name="Apple Maps Image Collection",
        category="Apple Maps",
        description="Regions, survey types and collection periods announced by Apple for France.",
        markdown=f"# {title}\n\n{body}",
    )


def extract_dsa(html: str, url: str) -> ThemeItem:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("main") or soup.select_one("article") or soup.select_one("#main")
    if container is None:
        raise ValueError("Apple DSA content not found")
    for unwanted in container.select("script, style, nav, form, button, [aria-hidden='true']"):
        unwanted.decompose()
    body = _to_markdown(container, url)
    if len(body) < 300:
        raise ValueError("Apple DSA content is unexpectedly short")
    title = "Apple — European Digital Services Act"
    return ThemeItem(
        item_id="policies:apple-dsa",
        collection="policies:apple-dsa",
        title=title,
        url=url,
        source_name="Apple Legal",
        category="DSA",
        description="Apple's DSA reports, disclosures, portals and policy information.",
        markdown=f"# {title}\n\n{body}",
    )


class ThematicWatcher:
    def __init__(self, root: Path, config: dict[str, Any], client: HttpClient, site_url: str, dry_run: bool = False) -> None:
        self.root = root
        self.config = config
        self.client = client
        self.site_url = site_url
        self.dry_run = dry_run
        self.created_events: list[Event] = []

    def _fetch_regulatory_collection(self, endpoint: str) -> tuple[str, list[ThemeItem]]:
        # A separate client makes concurrent reads safe while retaining retries.
        client = HttpClient(
            self.config["user_agent"], self.config["request_timeout_seconds"], 0
        )
        payload = client.get_json(
            f"{REGULATORY_BASE}/cwt/api/ext/{endpoint}", headers=REGULATORY_HEADERS
        )
        category = REGULATORY_COLLECTIONS[endpoint]
        return endpoint, [_regulatory_item(endpoint, category, record) for record in _records(payload)]

    def _fetch_source(self, source: dict[str, Any]) -> tuple[dict[str, list[ThemeItem]], dict[str, str]]:
        kind = source["type"]
        if kind == "regulatory_catalog":
            collections: dict[str, list[ThemeItem]] = {}
            errors: dict[str, str] = {}
            workers = int(self.config.get("regulatory_parallel_requests", 4))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._fetch_regulatory_collection, endpoint): endpoint for endpoint in REGULATORY_COLLECTIONS}
                for future in as_completed(futures):
                    endpoint = futures[future]
                    key = f"regulatory:{endpoint}"
                    try:
                        _, collections[key] = future.result()
                    except Exception as exc:
                        errors[key] = str(exc)
            return collections, errors

        url = source["url"]
        html = self.client.get_text(url)
        extractor = {
            "esim_france": extract_esim_france,
            "maps_france": extract_maps_france,
            "dsa": extract_dsa,
        }[kind]
        item = extractor(html, url)
        return {item.collection: [item]}, {}

    def _snapshot_path(self, slug: str, item_id: str) -> Path:
        name = hashlib.sha256(item_id.encode()).hexdigest()[:24]
        return self.root / "snapshots" / "themes" / slug / f"{name}.md"

    def _event(self, slug: str, kind: str, item: ThemeItem, timestamp: str, old: str = "") -> Event:
        marker = item.content_hash if kind != "removed" else timestamp
        digest = hashlib.sha256(f"{slug}|{item.item_id}|{kind}|{marker}".encode()).hexdigest()[:16]
        excerpt: list[str] = []
        added = removed = 0
        diff_page = None
        if kind == "updated":
            excerpt, added, removed = unified_changes(old, item.markdown, int(self.config["feed_diff_line_limit"]))
            stamp = timestamp.replace(":", "-")
            item_key = hashlib.sha256(item.item_id.encode()).hexdigest()[:16]
            diff_page = f"diffs/themes/{slug}/{item_key}/{stamp}.html"
            if not self.dry_run:
                write_html_diff(self.root / "public" / diff_page, old, item.markdown, item.title, item.url)
        return Event(
            event_id=f"apple-support-watch:{slug}:{kind}:{digest}",
            kind=kind,
            locale="fr-fr",
            article_id=item.item_id,
            title=f"[{item.category}] {item.title}",
            url=item.url,
            detected_at=timestamp,
            description=item.description,
            added=added,
            removed=removed,
            diff_excerpt=excerpt,
            diff_page=diff_page,
            source_name=item.source_name,
            category=item.category,
        )

    def run(self, timestamp: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for theme in self.config.get("themes", []):
            slug = theme["slug"]
            state_path = self.root / "state" / "themes" / f"{slug}.json"
            events_path = self.root / "events" / "themes" / f"{slug}.json"
            state = _load_json(state_path, {"items": {}, "initialized_collections": {}})
            records = state.setdefault("items", {})
            initialized = state.setdefault("initialized_collections", {})
            events = [Event.from_dict(value) for value in _load_json(events_path, [])]
            all_errors: dict[str, str] = {}
            fetched: dict[str, list[ThemeItem]] = {}

            for source in theme["sources"]:
                try:
                    collections, errors = self._fetch_source(source)
                    fetched.update(collections)
                    all_errors.update(errors)
                except Exception as exc:
                    all_errors[source["type"]] = str(exc)

            for collection, items in fetched.items():
                initial = collection not in initialized
                current_ids = {item.item_id for item in items}
                for item in items:
                    snapshot = self._snapshot_path(slug, item.item_id)
                    record = records.get(item.item_id)
                    old = snapshot.read_text(encoding="utf-8") if snapshot.exists() else ""
                    if record is None:
                        record = {
                            "collection": collection,
                            "first_seen": timestamp,
                            "active": True,
                            "missing_count": 0,
                        }
                        records[item.item_id] = record
                        if not initial:
                            event = self._event(slug, "new", item, timestamp)
                            events.insert(0, event)
                            self.created_events.append(event)
                    elif old and record.get("hash") and item.content_hash != record["hash"] and not initial:
                        event = self._event(slug, "updated", item, timestamp, old)
                        events.insert(0, event)
                        self.created_events.append(event)
                    record.update({
                        "collection": collection,
                        "title": item.title,
                        "url": item.url,
                        "source_name": item.source_name,
                        "category": item.category,
                        "description": item.description,
                        "hash": item.content_hash,
                        "last_checked": timestamp,
                        "active": True,
                        "missing_count": 0,
                    })
                    if not self.dry_run:
                        snapshot.parent.mkdir(parents=True, exist_ok=True)
                        snapshot.write_text(item.markdown, encoding="utf-8")

                if not initial:
                    confirmations = int(self.config["removal_confirmations"])
                    for item_id, record in records.items():
                        if record.get("collection") != collection or item_id in current_ids or not record.get("active", True):
                            continue
                        record["missing_count"] = int(record.get("missing_count", 0)) + 1
                        if record["missing_count"] >= confirmations:
                            record["active"] = False
                            vanished = ThemeItem(
                                item_id=item_id,
                                collection=collection,
                                title=record.get("title", item_id),
                                url=record.get("url", theme.get("link", "")),
                                source_name=record.get("source_name", "Apple"),
                                category=record.get("category", "Removed"),
                                description="This item disappeared from Apple's public catalogue in two consecutive checks.",
                                markdown="",
                            )
                            event = self._event(slug, "removed", vanished, timestamp)
                            events.insert(0, event)
                            self.created_events.append(event)
                initialized[collection] = initialized.get(collection) or timestamp

            state["last_success"] = timestamp
            state["errors"] = all_errors
            if not self.dry_run:
                _save_json(state_path, state)
                _save_json(events_path, [event.as_dict() for event in events[:1000]])
                write_feed(
                    self.root / "public" / "feeds" / f"{slug}.xml",
                    events,
                    theme["title"],
                    self.site_url,
                    int(self.config["feed_item_limit"]),
                )
            result[slug] = {
                "title": theme["title"],
                "active": sum(1 for record in records.values() if record.get("active", True)),
                "collections": len(initialized),
                "errors": all_errors,
            }
        return result
