from __future__ import annotations

import difflib
import html
from itertools import zip_longest
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


def _inline_diff(old: str, new: str) -> tuple[str, str]:
    previous: list[str] = []
    current: list[str] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        old_fragment = html.escape(old[old_start:old_end])
        new_fragment = html.escape(new[new_start:new_end])
        if tag == "equal":
            previous.append(old_fragment)
            current.append(new_fragment)
        elif tag == "delete":
            previous.append(f'<mark class="inline-remove">{old_fragment}</mark>')
        elif tag == "insert":
            current.append(f'<mark class="inline-add">{new_fragment}</mark>')
        else:
            previous.append(f'<mark class="inline-remove">{old_fragment}</mark>')
            current.append(f'<mark class="inline-add">{new_fragment}</mark>')
    return "".join(previous), "".join(current)


def _line(side: str, number: int | None, content: str, state: str, rendered: str | None = None) -> str:
    number_text = "" if number is None else str(number)
    body = html.escape(content) if rendered is None else rendered
    return (
        f'<div class="diff-line {side} {state}">'
        f'<span class="line-number">{number_text}</span>'
        f'<code class="line-text">{body}</code></div>'
    )


def _fold(hidden: int) -> str:
    label = "ligne inchangée masquée" if hidden == 1 else "lignes inchangées masquées"
    return f'<div class="fold"><span>••• {hidden} {label}</span></div>'


def _diff_rows(old_lines: list[str], new_lines: list[str], context: int = 3) -> tuple[str, int, int, int]:
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    opcodes = matcher.get_opcodes()
    groups = list(matcher.get_grouped_opcodes(n=context))
    added = sum(new_end - new_start for tag, _, _, new_start, new_end in opcodes if tag in {"insert", "replace"})
    removed = sum(old_end - old_start for tag, old_start, old_end, _, _ in opcodes if tag in {"delete", "replace"})

    if not groups:
        return '<div class="no-change">Aucune différence détectée.</div>', added, removed, 0

    rows: list[str] = []
    previous_old_end = 0
    previous_new_end = 0
    for group in groups:
        first = group[0]
        hidden = max(first[1] - previous_old_end, first[3] - previous_new_end)
        if hidden:
            rows.append(_fold(hidden))

        for tag, old_start, old_end, new_start, new_end in group:
            if tag == "equal":
                for offset, (old_line, new_line) in enumerate(
                    zip(old_lines[old_start:old_end], new_lines[new_start:new_end])
                ):
                    rows.append(_line("previous", old_start + offset + 1, old_line, "unchanged"))
                    rows.append(_line("current", new_start + offset + 1, new_line, "unchanged"))
                continue

            old_block = old_lines[old_start:old_end]
            new_block = new_lines[new_start:new_end]
            for offset, pair in enumerate(zip_longest(old_block, new_block)):
                old_line, new_line = pair
                if old_line is not None and new_line is not None:
                    old_rendered, new_rendered = _inline_diff(old_line, new_line)
                    rows.append(_line("previous", old_start + offset + 1, old_line, "removed", old_rendered))
                    rows.append(_line("current", new_start + offset + 1, new_line, "added", new_rendered))
                elif old_line is not None:
                    rows.append(_line("previous", old_start + offset + 1, old_line, "removed"))
                    rows.append(_line("current", None, "", "empty"))
                else:
                    rows.append(_line("previous", None, "", "empty"))
                    rows.append(_line("current", new_start + offset + 1, new_line or "", "added"))

        previous_old_end = group[-1][2]
        previous_new_end = group[-1][4]

    trailing = max(len(old_lines) - previous_old_end, len(new_lines) - previous_new_end)
    if trailing:
        rows.append(_fold(trailing))
    return "\n".join(rows), added, removed, len(groups)


def write_html_diff(path: Path, old: str, new: str, title: str, apple_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, added, removed, blocks = _diff_rows(old.splitlines(), new.splitlines())
    block_label = "bloc modifié" if blocks == 1 else "blocs modifiés"
    add_label = "ajout" if added == 1 else "ajouts"
    remove_label = "suppression" if removed == 1 else "suppressions"
    document = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{html.escape(title)} — Apple Support Watch</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      --background: #f5f5f7; --panel: #fff; --text: #1d1d1f; --muted: #6e6e73;
      --border: #d2d2d7; --gutter: #f0f0f2; --header: rgba(255,255,255,.94);
      --removed: #fff1f0; --removed-strong: #ffc8c3; --removed-text: #8a1c13;
      --added: #edfaef; --added-strong: #b9ebc1; --added-text: #176329;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--background); color: var(--text); }}
    main {{ width: min(1800px, 100%); margin: 0 auto; padding: 32px; }}
    .page-header {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 20px; }}
    .eyebrow {{ margin: 0 0 6px; color: var(--muted); font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
    h1 {{ margin: 0; max-width: 1100px; font-size: clamp(26px, 3vw, 42px); line-height: 1.08; letter-spacing: -.025em; }}
    .source {{ flex: 0 0 auto; border: 1px solid var(--border); border-radius: 999px; padding: 9px 14px; background: var(--panel); color: #06c; font-weight: 600; text-decoration: none; }}
    .source:hover {{ text-decoration: underline; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    .badge {{ border: 1px solid var(--border); border-radius: 999px; padding: 6px 10px; background: var(--panel); color: var(--muted); font-size: 13px; }}
    .badge.added {{ border-color: var(--added-strong); color: var(--added-text); }}
    .badge.removed {{ border-color: var(--removed-strong); color: var(--removed-text); }}
    .diff-scroll {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 14px; background: var(--panel); box-shadow: 0 8px 28px rgba(0,0,0,.06); }}
    .diff-grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); min-width: 860px; }}
    .pane-header {{ position: sticky; top: 0; z-index: 2; padding: 11px 16px; background: var(--header); border-bottom: 1px solid var(--border); backdrop-filter: blur(16px); font-size: 13px; font-weight: 700; }}
    .pane-header.previous {{ border-right: 1px solid var(--border); }}
    .diff-line {{ display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); min-width: 0; border-bottom: 1px solid color-mix(in srgb, var(--border) 55%, transparent); }}
    .diff-line.previous {{ border-right: 1px solid var(--border); }}
    .diff-line.removed {{ background: var(--removed); }}
    .diff-line.added {{ background: var(--added); }}
    .diff-line.empty {{ background: color-mix(in srgb, var(--gutter) 55%, transparent); }}
    .line-number {{ min-height: 100%; padding: 7px 10px 7px 6px; background: color-mix(in srgb, var(--gutter) 82%, transparent); color: var(--muted); text-align: right; user-select: none; font: 12px/1.55 ui-monospace, "SFMono-Regular", Menlo, monospace; }}
    .line-text {{ min-width: 0; margin: 0; padding: 7px 12px; color: inherit; white-space: pre-wrap; overflow-wrap: anywhere; word-break: normal; font: 13px/1.55 ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; }}
    mark {{ color: inherit; border-radius: 3px; padding: 1px 0; }}
    .inline-remove {{ background: var(--removed-strong); text-decoration: line-through; text-decoration-thickness: 1px; }}
    .inline-add {{ background: var(--added-strong); }}
    .fold {{ grid-column: 1 / -1; display: flex; align-items: center; gap: 12px; padding: 7px 16px; background: var(--gutter); color: var(--muted); border-bottom: 1px solid var(--border); font-size: 12px; text-align: center; }}
    .fold::before, .fold::after {{ content: ""; height: 1px; flex: 1; background: var(--border); }}
    .no-change {{ grid-column: 1 / -1; padding: 32px; text-align: center; color: var(--muted); }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --background: #151518; --panel: #1f1f23; --text: #f5f5f7; --muted: #a1a1a6; --border: #3a3a40; --gutter: #29292e; --header: rgba(31,31,35,.94); --removed: #3b2020; --removed-strong: #743630; --removed-text: #ffb4ad; --added: #183321; --added-strong: #285f37; --added-text: #9ee8ac; }}
      .source {{ color: #2997ff; }}
    }}
    @media (max-width: 700px) {{ main {{ padding: 18px 12px; }} .page-header {{ display: block; }} .source {{ display: inline-block; margin-top: 14px; }} }}
  </style>
</head>
<body>
  <main>
    <header class="page-header">
      <div><p class="eyebrow">Apple Support Watch · Comparaison</p><h1>{html.escape(title)}</h1></div>
      <a class="source" href="{html.escape(apple_url, quote=True)}">Voir l’article actuel ↗</a>
    </header>
    <div class="summary">
      <span class="badge added">+{added} {add_label}</span>
      <span class="badge removed">−{removed} {remove_label}</span>
      <span class="badge">{blocks} {block_label}</span>
      <span class="badge">Le texte inchangé est replié</span>
    </div>
    <div class="diff-scroll">
      <section class="diff-grid" aria-label="Comparaison des versions">
        <div class="pane-header previous">Version précédente</div>
        <div class="pane-header current">Version actuelle</div>
        {rows}
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")
