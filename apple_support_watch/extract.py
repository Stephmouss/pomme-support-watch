from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Article

SPACE_RE = re.compile(r"[ \t\f\v]+")
BLANK_RE = re.compile(r"\n{3,}")


def article_id_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def _clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("\u00a0", " ")).strip()


def _inline_text(node: Tag, base_url: str) -> str:
    clone_soup = BeautifulSoup(str(node), "html.parser")
    clone = clone_soup.find(node.name)
    if clone is None:
        return ""
    if node.name == "li":
        for nested_list in clone.find_all(["ul", "ol"]):
            nested_list.decompose()
    for link in clone.find_all("a"):
        label = _clean_text(link.get_text(" ", strip=True))
        href = link.get("href")
        if label and href:
            link.replace_with(f"[{label}]({urljoin(base_url, href)})")
        else:
            link.replace_with(label)
    return _clean_text(clone.get_text(" ", strip=True))


def _to_markdown(container: Tag, base_url: str) -> str:
    lines: list[str] = []
    consumed: set[int] = set()

    for node in container.find_all(["h1", "h2", "h3", "h4", "p", "li", "table", "img"]):
        if any(id(parent) in consumed for parent in node.parents if isinstance(parent, Tag)):
            continue
        if node.name == "p" and node.find_parent("li") is not None:
            continue
        if node.name == "table":
            consumed.add(id(node))
            rows = []
            for row in node.find_all("tr"):
                cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                lines.extend(rows)
            continue
        if node.name == "img":
            alt = _clean_text(node.get("alt", ""))
            if alt:
                lines.append(f"[Image: {alt}]")
            continue
        text = _inline_text(node, base_url)
        if not text:
            continue
        if node.name and node.name.startswith("h"):
            level = min(int(node.name[1]), 4)
            lines.append(f"{'#' * level} {text}")
        elif node.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)

    # Stable line-oriented output makes Git and RSS diffs readable.
    output: list[str] = []
    previous = None
    for line in lines:
        line = _clean_text(line)
        if line and line != previous:
            output.append(line)
            previous = line
    return "\n\n".join(output).strip() + "\n"


def extract_article(html: str, url: str, locale: str) -> Article:
    soup = BeautifulSoup(html, "html.parser")
    title_meta = soup.select_one('meta[property="og:title"]')
    description_meta = soup.select_one('meta[name="description"]')
    title = title_meta.get("content", "") if title_meta else ""
    title = re.sub(r"\s+-\s+Apple Support$", "", _clean_text(title))
    description = _clean_text(description_meta.get("content", "")) if description_meta else ""

    container = soup.select_one("#content #sections") or soup.select_one("#sections")
    if container is None:
        container = soup.select_one("article") or soup.select_one("main")
    if container is None:
        raise ValueError(f"Article content not found: {url}")

    for unwanted in container.select(
        "script, style, nav, form, button, .feedback, .helpful, [aria-hidden='true']"
    ):
        unwanted.decompose()

    markdown = _to_markdown(container, url)
    if title and not markdown.startswith("# "):
        markdown = f"# {title}\n\n{description}\n\n{markdown}" if description else f"# {title}\n\n{markdown}"
    if len(markdown) < 80:
        raise ValueError(f"Extracted article is unexpectedly short: {url}")

    date_node = soup.select_one("time, .published-date, #publication-date")
    published_date = _clean_text(date_node.get_text(" ", strip=True)) if date_node else None
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return Article(
        url=url,
        article_id=article_id_from_url(url),
        locale=locale,
        title=title or article_id_from_url(url),
        description=description,
        markdown=markdown,
        published_date=published_date,
        content_hash=digest,
    )
