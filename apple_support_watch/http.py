from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class HttpClient:
    user_agent: str
    timeout: float = 30
    delay: float = 0.35

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xml,text/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8,fr;q=0.6",
            }
        )
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self._last_request = 0.0

    def get_text(self, url: str) -> str:
        return self._get(url).text

    def get_json(self, url: str, headers: dict[str, str] | None = None):
        return self._get(url, headers=headers).json()

    def _get(self, url: str, headers: dict[str, str] | None = None):
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        response = self.session.get(url, timeout=self.timeout, headers=headers)
        self._last_request = time.monotonic()
        response.raise_for_status()
        return response
