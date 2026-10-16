"""Local, explainable editorial rules for Apple's regulatory model references."""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Event

MODEL = re.compile(r"(?<![A-Za-z0-9])A\d{4}(?![A-Za-z0-9])", re.I)


def models(description: str) -> list[str]:
    # Only the explicit model field, never arbitrary IDs inside document JSON.
    field = re.search(r"Models:\s*(.*?)(?:\s*·|$)", description)
    return sorted({m.upper() for m in MODEL.findall(field.group(1))}) if field else []


def signature(name: str) -> str:
    name = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c))
    name = re.sub(r"\b(pour|for|de|du|the|apple|case|etui)\b", " ", name)
    name = re.sub(r"\b(pouces?|inches)\b", "inch", name)
    name = re.sub(r"\b(\d+)(?:st|nd|rd|th|eme|e)?\s*(?:generation|gen)\b", r"gen \1", name)
    return " ".join(sorted(set(re.findall(r"[a-z0-9]+", name))))


def family(name: str) -> str:
    text = signature(name)
    if "ipad" in text:
        accessory = "Smart Folio pour " if "folio" in text else "Smart Cover pour " if "cover" in text else ""
        device = "iPad mini" if "mini" in text else "iPad Air" if "air" in text else "iPad Pro" if "pro" in text else "iPad"
        return accessory + device
    for word, label in (("iphone", "iPhone"), ("macbook", "MacBook"), ("airpods", "AirPods"),
                        ("homepod", "HomePod"), ("watch", "Apple Watch"), ("magsafe", "MagSafe")):
        if word in text.split():
            return label
    return name


def informative(name: str, category: str) -> bool:
    return bool(name and name != category and not name.startswith(category + " —"))


class ReferenceFilter:
    def __init__(self, previous: dict, records: dict, items: list, timestamp: str, initialized: set[str]):
        self.timestamp = timestamp
        self.migration = not previous
        # JSON roundtrip isolates the index from watcher state during dry runs.
        self.index = json.loads(json.dumps(previous)) if previous else {
            "version": 1, "activated_at": timestamp, "models": {}, "alerts": [],
            "totals": {"new_references": 0, "identity_changes": 0, "duplicate_sections": 0},
        }
        self.before = records
        self.decisions: dict[str, dict] = {}
        self.metrics = {"new_references": 0, "identity_changes": 0, "duplicate_sections": 0}
        self.emitted: set[tuple] = set()
        if self.migration:
            # Baseline all previous sections together; never replay old models.
            for record in records.values():
                if not record.get("collection", "").startswith("regulatory:"):
                    continue
                for model in models(record.get("description", "")):
                    self._observe(model, record.get("title", ""), record["collection"], record.get("first_seen", timestamp), historical=True)
        known = set(self.index["models"])
        regulatory = sorted((i for i in items if i.collection.startswith("regulatory:")),
                            key=lambda i: (i.collection != "regulatory:device/regulatory_data", i.item_id))
        new_owner: dict[str, str] = {}
        for item in regulatory:
            refs = models(item.description)
            new = [m for m in refs if m not in known]
            owned = [m for m in new if item.collection in initialized
                     and new_owner.setdefault(m, item.item_id) == item.item_id]
            old = records.get(item.item_id, {})
            old_refs = set(models(old.get("description", "")))
            renamed = bool(refs and old_refs.intersection(refs)
                           and informative(item.title, item.category)
                           and informative(old.get("title", ""), item.category)
                           and signature(item.title) != signature(old.get("title", "")))
            self.decisions[item.item_id] = {"models": refs, "new": new, "owned": owned,
                                           "renamed": renamed, "old_title": old.get("title", "")}
            for model in refs:
                self._observe(model, item.title, item.collection, timestamp,
                              historical=self.migration and model not in known)

    def _observe(self, model, name, collection, first_seen, historical=False):
        entry = self.index["models"].setdefault(model, {
            "first_seen": first_seen, "names": [], "collections": [],
            "historical": historical,
        })
        entry["first_seen"] = min(entry["first_seen"], first_seen)
        entry["last_seen"] = self.timestamp
        if (name or model) not in entry["names"]:
            entry["names"].append(name or model)
        if collection not in entry["collections"]:
            entry["collections"].append(collection)

    def apply(self, event: Event, item) -> Event | None:
        decision = self.decisions.get(item.item_id, {})
        refs = decision.get("models", [])
        if not refs:
            return event
        if self.migration:
            # Existing per-document monitoring still operates during activation.
            return event
        owned = decision["owned"]
        if owned:
            reason = "new_reference"
            selected = owned
            context = "Référence jamais observée dans l’ensemble des rubriques Regulatory surveillées."
            self.metrics["new_references"] += len(owned)
        elif decision["new"]:
            self.metrics["duplicate_sections"] += 1
            return None
        elif decision["renamed"]:
            reason = "identity_change"
            selected = refs
            context = f"Nom du produit modifié pour une référence connue : « {decision['old_title']} » → « {item.title} »."
            key = (tuple(refs), signature(item.title))
            if key in self.emitted:
                return None
            self.emitted.add(key)
            self.metrics["identity_changes"] += 1
        elif event.kind == "new":
            # Same hardware, newly listed section: retain it in the index only.
            self.metrics["duplicate_sections"] += 1
            return None
        else:
            return event  # Actual changes to an existing regulatory document.
        event.editorial_type = reason
        event.reference_models = selected
        event.reference_context = (context + " Première détection : " + self.timestamp
            + ". Famille : " + family(item.title) + ". "
            + "Cela ne prouve pas qu’un produit est non annoncé ; une variante ou un accessoire déjà commercialisé reste possible.")
        event.title = item.title + " — " + ", ".join(selected)
        marker = ",".join(selected) + (":" + signature(item.title) if reason == "identity_change" else "")
        event.event_id = "apple-regulatory:" + reason + ":" + hashlib.sha256(marker.encode()).hexdigest()[:20]
        event.reference_page = "references/index.html#" + selected[0]
        self.index["alerts"].append({"event_id": event.event_id, "type": reason,
            "detected_at": self.timestamp, "models": selected, "title": item.title,
            "description": item.description, "context": event.reference_context, "url": item.url})
        return event

    def finish(self):
        for key, count in self.metrics.items():
            self.index["totals"][key] = self.index["totals"].get(key, 0) + count
        self.index["last_run"] = {"checked_at": self.timestamp, "baseline": self.migration, **self.metrics}
        return self.index


def write_archive(public: Path, index: dict) -> None:
    destination = public / "references"
    destination.mkdir(parents=True, exist_ok=True)
    models_index = index["models"]
    alerts = sorted(index["alerts"], key=lambda a: a["detected_at"], reverse=True)
    e = html.escape
    cutoff = datetime.fromisoformat(index["last_run"]["checked_at"].replace("Z", "+00:00")) - timedelta(days=7)
    recent = [a for a in alerts if datetime.fromisoformat(a["detected_at"].replace("Z", "+00:00")) >= cutoff]
    body = ('<h1>Références matérielles Apple</h1><p>Historique commun aux rubriques Regulatory. '
            'Une nouvelle référence n’est pas une preuve de produit non annoncé.</p>'
            f'<p>Filtre activé le {e(index["activated_at"])}. {len(models_index)} références mémorisées.</p>'
            f'<p>Depuis l’activation : {index["totals"]["new_references"]} nouvelle(s) référence(s), '
            f'{index["totals"]["identity_changes"]} changement(s) de nom et '
            f'{index["totals"]["duplicate_sections"]} apparition(s) dans une autre rubrique écartée(s) du RSS.</p>'
            f'<h2>Sur les sept derniers jours</h2><p>{len(recent)} signalement(s) du filtre.</p>'
            '<h2>Signalements depuis l’activation</h2>')
    for a in alerts:
        body += (f'<article><h3>{e(a["title"])} — {e(", ".join(a["models"]))}</h3>'
                 f'<p>{e(a["context"])}</p><p>{e(a["description"])}</p>'
                 f'<p><a href="{e(a["url"], quote=True)}">Source Apple</a></p></article>')
    if not alerts:
        body += '<p>Aucun signalement depuis l’activation. Les références antérieures ne sont pas renvoyées dans le RSS.</p>'
    body += '<h2>Registre conservé</h2><p>Les dates ci-dessous sont celles de notre collecte, pas des dates de publication garanties par Apple. Les références déjà connues à l’activation servent de base de comparaison.</p>'
    for model, record in sorted(models_index.items(), key=lambda kv: (kv[1]["first_seen"], kv[0]), reverse=True):
        body += (f'<details id="{e(model)}"><summary>{e(model)} — {e(record["names"][0])}</summary>'
                 f'<p>Première observation : {e(record["first_seen"])}.</p>'
                 f'<p>Noms observés : {e(" ; ".join(record["names"]))}.</p>'
                 f'<p>Rubriques : {e(" ; ".join(record["collections"]))}.</p></details>')
    document = ('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Références matérielles Apple</title><style>body{font:17px/1.6 system-ui;max-width:900px;margin:40px auto;padding:0 20px}details,article{padding:12px 0;border-bottom:1px solid #ddd}summary{cursor:pointer}a{color:#065bb5}</style>'
                '<body>' + body + '</body></html>')
    (destination / "index.html").write_text(document, encoding="utf-8")
    # Small structured archive for future reuse; no extra requests or AI calls.
    (destination / "references.json").write_text(json.dumps({
        "activated_at": index["activated_at"], "last_run": index["last_run"],
        "totals": index["totals"], "alerts": alerts,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
