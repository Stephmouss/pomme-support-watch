from __future__ import annotations

import difflib
import html
from pathlib import Path


def unified_changes(old: str, new: str, limit: int = 80) -> tuple[list[str], int, int]:
    raw = list(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), fromfile="Previous", tofile="Current", n=2, lineterm=""
        )
    )
    changed = [line for line in raw if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    added = sum(1 for line in changed if line.startswith("+"))
    removed = sum(1 for line in changed if line.startswith("-"))
    return changed[:limit], added, removed


def write_html_diff(path: Path, old: str, new: str, title: str, apple_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = difflib.HtmlDiff(tabsize=2, wrapcolumn=100).make_table(
        old.splitlines(), new.splitlines(), fromdesc="Previous version", todesc="Current version", context=False
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{html.escape(title)} — Apple Support Watch</title>
  <style>
    :root {{ color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    body {{ margin: 0 auto; max-width: 1500px; padding: 24px; }}
    a {{ color: #06c; }} .meta {{ margin-bottom: 24px; color: #666; }}
    table.diff {{ border-collapse: collapse; width: 100%; table-layout: fixed; font-family: ui-monospace, monospace; font-size: 13px; }}
    .diff_header {{ background: #e8e8ed; color: #222; }}
    td {{ padding: 2px 6px; vertical-align: top; overflow-wrap: anywhere; }}
    .diff_add {{ background: #c6f6d5; color: #111; }} .diff_sub {{ background: #fed7d7; color: #111; }}
    .diff_chg {{ background: #fefcbf; color: #111; }}
    @media (prefers-color-scheme: dark) {{ .meta {{ color:#aaa; }} a {{color:#2997ff}} }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="meta"><a href="{html.escape(apple_url, quote=True)}">Current article on Apple Support</a></p>
  {table}
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")

