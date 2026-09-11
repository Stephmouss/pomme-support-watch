from __future__ import annotations

import html
import json
from pathlib import Path


def write_index(public_dir: Path, status: dict, site_title: str) -> None:
    public_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for locale, details in status["sources"].items():
        cards.append(
            f"<section><h2>{html.escape(locale)}</h2>"
            f"<p><strong>{details['active']}</strong> active articles</p>"
            f"<p>{details['baselined']} snapshots · {details['pending']} pending</p>"
            f"<p><a href=\"feeds/{locale}-new.xml\">New articles</a> · "
            f"<a href=\"feeds/{locale}-updated.xml\">Updated articles</a></p></section>"
        )
    for slug, details in status.get("themes", {}).items():
        warning = f"<p>⚠ {len(details['errors'])} unavailable collection(s)</p>" if details.get("errors") else ""
        cards.append(
            f"<section><h2>{html.escape(details['title'])}</h2>"
            f"<p><strong>{details['active']}</strong> watched items · "
            f"{details['collections']} collections</p>{warning}"
            f"<p><a href=\"feeds/{html.escape(slug)}.xml\">All changes</a></p></section>"
        )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(site_title)}</title>
<style>body{{font:17px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:60px auto;padding:0 24px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}}section{{border:1px solid #d2d2d7;border-radius:14px;padding:20px}}code{{background:#eee;padding:2px 5px}}a{{color:#06c}}</style></head>
<body><h1>{html.escape(site_title)}</h1><p>Last successful check: <code>{html.escape(status['last_success'])}</code></p>
<main>{''.join(cards)}</main><p>This independent project is not affiliated with or endorsed by Apple.</p></body></html>"""
    (public_dir / "index.html").write_text(page, encoding="utf-8")
    (public_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (public_dir / ".nojekyll").write_text("", encoding="utf-8")
