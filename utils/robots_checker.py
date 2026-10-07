"""
robots_checker.py
Checks robots.txt for a domain before scraping it, and caches results
per domain for the duration of the run.
"""

import urllib.robotparser
import urllib.request
import urllib.error
from urllib.parse import urlparse

_cache = {}


def is_allowed(url: str, user_agent: str = "*") -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    if base not in _cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            # We use urllib.request with a timeout and a browser user-agent to avoid being hung or blocked.
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
            req = urllib.request.Request(f"{base}/robots.txt", headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                content = response.read().decode("utf-8")
                rp.parse(content.splitlines())
            _cache[base] = rp
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                rp.disallow_all = True
                _cache[base] = rp
            elif err.code >= 400:
                rp.allow_all = True
                _cache[base] = rp
            else:
                _cache[base] = None
        except Exception:
            _cache[base] = None

    rp = _cache[base]
    if rp is None:
        return False

    return rp.can_fetch(user_agent, url)
