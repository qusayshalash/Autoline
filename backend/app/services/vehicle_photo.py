"""A representative photo of a vehicle's model.

The registry holds no images. What can be shown is a photo of the *model* - a Kia Picanto,
not this Kia Picanto - and the screen says so under the picture, because a photo that looks
like the car in front of somebody is easily read as being it.

The source is Wikipedia's page search, which returns a lead image for the page it finds.
Checked against ten of the registry's commonest models before building on it: all ten found
the right article, including the Mitsubishi Attrage under its other name, Mirage. One thing
broke it: the registry writes the make together with its country of manufacture - "קיה
סלובקיה", Kia Slovakia - and "Kia Slovakia PICANTO" finds a list of Kia's factories. So the
caller sends the make without its country; the screen holds the dictionary that knows which
words are countries.

Looked up here rather than from the browser, for three reasons: one answer per model is
cached for everybody instead of asked again by every visitor; Wikimedia asks API clients for
a descriptive User-Agent, which a browser cannot set; and an installation with no internet
access can switch it off in one place (CATALOG_PHOTOS=false). The image itself is still
loaded by the browser, from Wikimedia, which permits it.
"""

import json
import re
import threading
import time
import unicodedata
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import settings

SEARCH_URL = "https://en.wikipedia.org/w/rest.php/v1/search/page"
USER_AGENT = "Autoline/1.0 (vehicle registry catalog lookup)"
TIMEOUT_S = 4.0

# The search returns a 60-pixel thumbnail; Wikimedia renders other widths by rewriting the
# size in the path - but only its standard steps. Measured on 2026-10-03: 330, 500 and 960
# came back as images; 640 came back as HTTP 400, and every photo the catalog offered was a
# broken image until this was found. 500 is a standard step, served from both hosts, and
# enough for a card a few hundred pixels wide.
WIDTH = 500

# A model nobody can find stays unfound for a day before it is asked about again - long
# enough not to ask Wikipedia about the same obscure model on every lookup, short enough
# that a page created later is picked up.
MISS_TTL_S = 24 * 3600

_lock = threading.Lock()
_cache: dict[str, dict] = {}
_loaded = False


def _cache_path():
    return settings.data_dir / "photo_cache.json"


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # an entry saved at another width is dropped rather than served: the first
            # version saved 640px addresses, which Wikimedia refuses, and a saved hit
            # survives restarts - so without this the fix would never reach those models
            current = f"/{WIDTH}px-"
            _cache.update(
                {
                    k: v
                    for k, v in data.items()
                    if isinstance(v, dict) and current in (v.get("url") or "")
                }
            )
    except (OSError, ValueError):
        pass


def _save() -> None:
    # only hits are kept on disk: a miss is a statement about today, a hit about the model
    hits = {k: v for k, v in _cache.items() if v.get("url")}
    try:
        _cache_path().write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _fold(text: str) -> str:
    """Lower case without accents, so "Škoda" in a title matches "Skoda" typed."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _key(make: str, model: str) -> str:
    return f"{_fold(make).strip()}|{_fold(model).strip()}"


# The hosts Wikimedia serves images from. Checked against the real response rather than
# assumed: the search's thumbnails come from thumb.wikimedia.org - the first version of this
# accepted only upload.wikimedia.org, and turned away every image while its own test, mocked
# with the assumed host, passed.
IMAGE_HOSTS = {"upload.wikimedia.org", "thumb.wikimedia.org"}


def _larger(thumb_url: str) -> Optional[str]:
    """The same image at WIDTH pixels, from a Wikimedia host, without the tracking
    parameters the search appends. Whatever the search returns is not trusted to be an
    image host, so the host is compared exactly rather than by prefix."""
    if not thumb_url:
        return None
    url = "https:" + thumb_url if thumb_url.startswith("//") else thumb_url
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
        return None
    path = re.sub(r"/\d+px-", f"/{WIDTH}px-", parts.path, count=1)
    # utm_source and friends identify the referring page to Wikimedia's analytics; there
    # is no reason to forward them from somebody else's screen
    return urlunsplit(("https", parts.hostname, path, "", ""))


def _plausible(title: str, make: str, model: str) -> bool:
    """Whether the page found is about a car of this make.

    The search always returns *something*. Without this, an unknown model would be shown
    a photo of whatever ranked first - a factory list, a disambiguation page, another
    make's car - under a caption saying it is this vehicle's model.
    """
    t = _fold(title)
    if t.startswith("list of") or "(disambiguation)" in t:
        return False
    first = _fold(make).split()[0] if make.strip() else ""
    return bool(first) and first in t


def find(make: str, model: str, *, client: Optional[httpx.Client] = None) -> dict:
    """{url, title, page} for a representative photo, or {url: None} when there is none."""
    make, model = (make or "").strip(), (model or "").strip()
    if not settings.catalog_photos or not make:
        return {"url": None}
    key = _key(make, model)

    with _lock:
        _load()
        hit = _cache.get(key)
    if hit and (hit.get("url") or time.time() - hit.get("at", 0) < MISS_TTL_S):
        return {k: hit.get(k) for k in ("url", "title", "page")}

    result: dict = {"url": None}
    own = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    try:
        r = http.get(SEARCH_URL, params={"q": f"{make} {model}".strip(), "limit": 3})
        if r.status_code == 200:
            for page in r.json().get("pages", []):
                url = _larger((page.get("thumbnail") or {}).get("url", ""))
                title = page.get("title") or ""
                if url and _plausible(title, make, model):
                    result = {
                        "url": url,
                        "title": title,
                        "page": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                    }
                    break
    except (httpx.HTTPError, ValueError):
        # a network failure is not cached as a miss: it says nothing about the model
        return {"url": None}
    finally:
        if own:
            http.close()

    with _lock:
        _cache[key] = {**result, "at": time.time()}
        if result.get("url"):
            _save()
    return result


def clear() -> None:
    """For tests."""
    global _loaded
    with _lock:
        _cache.clear()
        _loaded = True
