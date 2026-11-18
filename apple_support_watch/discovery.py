"""Find recent Support articles missing from Apple's XML sitemaps."""
from datetime import date
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .sitemaps import canonical_article_url


def search_candidates(client, queries: list[str]) -> tuple[list[str], dict[str, str]]:
    results = []
    errors = {}
    for query in queries:
        try:
            slug = quote(query.replace(" ", "-"), safe="")
            html = client.get_text(f"https://www.apple.com/us/search/{slug}?src=globalnav&tab=support")
            soup = BeautifulSoup(html, "html.parser")
            links = soup.select("a.rf-serp-support-title-link[href]")
            if not links:
                raise ValueError("Aucun résultat Support exploitable")
            ids = []
            for link in links:
                url = canonical_article_url(link["href"])
                match = re.fullmatch(r"https://support\.apple\.com/en-us/(\d+)", url)
                if match and match[1] not in ids:
                    ids.append(match[1])
            results.append(ids[:12])
        except Exception as exc:
            errors[query] = str(exc)
    # Interleave subjects so one broad query cannot fill the request budget.
    return list(dict.fromkeys(
        ids[i] for i in range(12) for ids in results if i < len(ids)
    )), errors


def publication_date(value: str | None) -> date | None:
    if not value:
        return None
    months = (
        "january february march april may june july august september october november december".split(),
        "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(),
    )
    value = " ".join(value.lower().split())
    try:
        if match := re.fullmatch(r"([a-z]+) (\d{1,2}), (\d{4})", value):
            return date(int(match[3]), months[0].index(match[1]) + 1, int(match[2]))
        if match := re.fullmatch(r"(\d{1,2})(?:er)? (\w+) (\d{4})", value):
            return date(int(match[3]), months[1].index(match[2]) + 1, int(match[1]))
        return date.fromisoformat(value)
    except ValueError:
        return None
