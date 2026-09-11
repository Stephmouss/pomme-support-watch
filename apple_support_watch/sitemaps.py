from __future__ import annotations

from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .http import HttpClient

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_sitemap_index(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    urls = []
    for node in root.findall("sm:sitemap/sm:loc", NS):
        if node.text and "-ac-" in node.text and node.text.endswith(".xml"):
            urls.append(node.text.strip())
    return urls


def parse_urlset(xml: str, expected_locale: str | None = None) -> dict[str, str | None]:
    root = ET.fromstring(xml)
    result: dict[str, str | None] = {}
    for item in root.findall("sm:url", NS):
        loc = item.findtext("sm:loc", namespaces=NS)
        if not loc:
            continue
        loc = loc.strip()
        if expected_locale and f"/{expected_locale}/" not in urlparse(loc).path:
            continue
        lastmod = item.findtext("sm:lastmod", namespaces=NS)
        result[loc] = lastmod.strip() if lastmod else None
    return result


def fetch_articles(client: HttpClient, index_url: str, locale: str) -> dict[str, str | None]:
    index_xml = client.get_text(index_url)
    sitemap_urls = parse_sitemap_index(index_xml)
    if not sitemap_urls:
        raise ValueError(f"No article sitemap found in {index_url}")
    articles: dict[str, str | None] = {}
    for sitemap_url in sitemap_urls:
        articles.update(parse_urlset(client.get_text(sitemap_url), locale))
    if len(articles) < 100:
        raise ValueError(f"Suspiciously small sitemap for {locale}: {len(articles)} URLs")
    return articles

