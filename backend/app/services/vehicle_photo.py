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


def _user_agent() -> str:
    """Wikimedia's rules: a client naming a contact gets 200 requests a minute, one that
    does not gets 10. The contact is the operator's to give (CATALOG_PHOTO_CONTACT)."""
    contact = (settings.catalog_photo_contact or "").strip()
    return f"Autoline/1.0 ({contact}; vehicle registry catalog lookup)" if contact else USER_AGENT
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


# Bumped whenever what a saved answer means changes, so answers chosen by an older rule
# are dropped rather than served from disk for ever. Version 2: the first rule accepted
# any page whose title held the make, and saved "Chrysler Hemi engine" as the photo of a
# Grand Cherokee on a real installation; a saved hit survives restarts, so without the
# version that engine would have kept standing in for the car.
CACHE_VERSION = 2


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or data.get("_version") != CACHE_VERSION:
        return
    current = f"/{WIDTH}px-"
    for k, v in (data.get("entries") or {}).items():
        if isinstance(v, dict) and (current in (v.get("url") or "") or v.get("generations") is not None):
            _cache[k] = v


def _save() -> None:
    # hits only: a miss is a statement about today, a hit about the model
    hits = {k: v for k, v in _cache.items() if v.get("url") or v.get("generations")}
    try:
        _cache_path().write_text(
            json.dumps({"_version": CACHE_VERSION, "entries": hits}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
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


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(text))


# Pages the search returns that are about something other than a car of this model. The
# second of these was found on a real installation: "Chrysler Hemi engine" shown, under a
# caption naming the model, as the photo of a Grand Cherokee.
_NOT_A_CAR = re.compile(
    r"\bengines?\b|company|subsidiary|manufacturer|factory|plant|division|brand|platform|"
    r"transmission|motorsport|racing|^list of|disambiguation",
    re.I,
)
_A_CAR = re.compile(
    r"\b(cars?|automobiles?|vehicles?|suv|hatchback|sedan|saloon|crossover|minivan|mpv|"
    r"pickup|van|truck|coupe|roadster|estate|wagon)\b",
    re.I,
)

# A model name this long names the car by itself: "grandcherokee" is a Jeep whichever
# company the registry files it under. A short one - "3", "208", "i10" - needs the make
# beside it to mean anything.
DISTINCTIVE = 5


def _choose(pages: list[dict], make: str, model: str) -> Optional[dict]:
    """The first search result that is a page about this car, or None.

    The search always returns *something*, and a wrong car under a caption naming this
    model is worse than no picture. So a page has to earn it: not about an engine, a
    company or a list; and either named after the model, or described as a car of this
    make whose text the search matched on the model's name - which is how the Attrage is
    found inside the Mirage article it redirects to.
    """
    make_word = _fold(make).split()[0] if make.strip() else ""
    want = _compact(model)
    for page in pages:
        title = page.get("title") or ""
        description = page.get("description") or ""
        # the description vetoes only when it is not about a car: "a compact car sold
        # under the Kia brand" is a car page, "series of V8 engines built by Chrysler" not
        if _NOT_A_CAR.search(title) or (
            _NOT_A_CAR.search(description) and not _A_CAR.search(description)
        ):
            continue
        has_make = bool(make_word) and make_word in _fold(title)
        if want and want in _compact(title) and (has_make or len(want) >= DISTINCTIVE):
            return page
        excerpt = re.sub(r"<[^>]+>", "", page.get("excerpt") or "")
        if has_make and want and _A_CAR.search(description) and want in _compact(excerpt):
            return page
    return None


# ---- the right generation -------------------------------------------------------------
#
# The article's lead image is its newest generation. A 2016 Picanto was shown a 2018
# redesign; that is a different-looking car, and the reader has no way to know. Wikipedia's
# car articles split each generation into its own section headed with its first year -
# "Second generation (TA; 2011)" - and checked on nine of the registry's commonest models,
# every one did. So with the vehicle's year, the photo comes from its own generation's
# section, and the caption can say which years that is.
#
# Colour is not matched. No free source does it reliably - Commons searched by model, year
# and colour returned a Mazda CX-7 for a Mazda 3 and a painting for an Octavia - and the
# caption says so rather than letting a blue car stand for a silver one.

API_URL = "https://en.wikipedia.org/w/api.php"
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
# A level-two heading in source text: "== Second generation (TA; 2011) =="
_HEADING = re.compile(r"(?m)^==\s*([^=].*?)\s*==\s*$")
# A photo named in a section: the infobox's "| image = ...", a gallery's "| image1 = ...",
# or an inline [[File:...]]. The numbered form was missed at first, and every Corolla
# from 2012 on - whose generations are shown in galleries - fell back to the newest one.
_FILE = re.compile(
    r"(?:\|\s*image\d*\s*=\s*(?:\[\[(?:File|Image):)?|\[\[(?:File|Image):)"
    r"\s*([^|\]\n}]+?\.(?:jpe?g|png|webp))",
    re.I,
)

# Front views first; rear, interior and engine shots last. A section often opens with a
# rear view or a dashboard - measured on the i10 and the Mazda3 - which is not the picture
# somebody uses to recognise a car.
_FRONT = re.compile(r"front|vorder|avant|frontal|\b3\.?4\b", re.I)
_NOT_THE_CAR = re.compile(
    r"rear|heck|back|interior|innenraum|dashboard|cockpit|engine|motor|trunk|boot|seat|"
    r"logo|flag|icon|emblem|badge|symbol|map|diagram",
    re.I,
)

# Wikimedia answers a burst of API calls with 429 - which is what the first prototype of
# this got. Calls are serialised and spaced; with every answer cached, the spacing is paid
# once per model and once per generation, not per lookup.
MIN_INTERVAL_S = 1.0
# Without a contact Wikimedia allows 10 a minute; 6.5 seconds apart stays under it.
ANONYMOUS_INTERVAL_S = 6.5


def _interval() -> float:
    return MIN_INTERVAL_S if (settings.catalog_photo_contact or "").strip() else ANONYMOUS_INTERVAL_S

# Longest a refused call waits before its one retry. Longer than this and the person looking
# at the card is better served by no photo now and one on the next lookup.
MAX_RETRY_WAIT_S = 5.0
_pace_lock = threading.Lock()
_last_call = 0.0


class _Busy(Exception):
    """Wikimedia asked us to slow down. Nothing is cached on the strength of it."""


def _get(http: httpx.Client, url: str, params: dict) -> dict:
    """Every call to Wikimedia goes through here, spaced and serialised. The first version
    paced the generation calls but not the search in front of them, and a run of ten
    lookups had the search refused for seven of them."""
    global _last_call
    for attempt in (1, 2):
        with _pace_lock:
            wait = _interval() - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                r = http.get(url, params=params)
            finally:
                _last_call = time.monotonic()
        if r.status_code != 429 or attempt == 2:
            break
        # Told to wait: wait as long as asked, once, if that is short. A run of a dozen
        # new models was refused from the twelfth call on without this; with it the photo
        # arrives a few seconds later instead of not at all.
        try:
            delay = float(r.headers.get("retry-after") or MAX_RETRY_WAIT_S)
        except ValueError:
            delay = MAX_RETRY_WAIT_S
        if delay > MAX_RETRY_WAIT_S:
            break
        time.sleep(delay)
    if r.status_code == 429 or r.status_code >= 500:
        raise _Busy(r.status_code)
    r.raise_for_status()
    return r.json()


def _api(http: httpx.Client, params: dict) -> dict:
    return _get(http, API_URL, {**params, "format": "json", "formatversion": 2})


def _generations(http: httpx.Client, title: str) -> list[list]:
    """[[first_year, anchor, [photo files...]], ...] for an article, cached per article.

    Read from the article's source text with one ordinary query, not from Wikipedia's
    parser. The first version asked the parser for the section list and then for each
    section's images, and Wikimedia refuses parse requests after only a few - measured:
    the fifth came back 429. The source holds both answers: the level-two headings carry
    each generation's first year, and the infobox under each heading names its photo.
    """
    key = f"sections|{title}"
    with _lock:
        hit = _cache.get(key)
    if hit is not None and hit.get("generations") is not None:
        return hit["generations"]
    data = _api(
        http,
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": title,
            "redirects": 1,
        },
    )
    pages = (data.get("query") or {}).get("pages") or [{}]
    revisions = pages[0].get("revisions") or [{}]
    text = ((revisions[0].get("slots") or {}).get("main") or {}).get("content") or ""

    headings = [(m.start(), m.group(1)) for m in _HEADING.finditer(text)]
    out = []
    for i, (at, raw) in enumerate(headings):
        heading = re.sub(r"<[^>]+>", "", raw).strip()
        year = _YEAR.search(heading)
        if "generation" not in heading.lower() or not year:
            continue
        end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        files = [f.strip() for f in _FILE.findall(text[at:end])]
        out.append([int(year.group(1)), heading.replace(" ", "_"), files])
    with _lock:
        _cache[key] = {"generations": out, "at": time.time()}
        _save()
    return out


def _rank(files: list[str]) -> list[str]:
    photos = [f for f in files if re.search(r"\.(jpe?g|png|webp)$", f, re.I)]
    keep = [f for f in photos if not _NOT_THE_CAR.search(f)]
    # front views to the front, the rest in the article's own order
    return sorted(keep, key=lambda f: 0 if _FRONT.search(f) else 1)


def _file_url(http: httpx.Client, name: str) -> Optional[str]:
    """A file's address at WIDTH pixels, cached per file."""
    key = f"file|{name}"
    with _lock:
        hit = _cache.get(key)
    if hit is not None and (hit.get("url") or time.time() - hit.get("at", 0) < MISS_TTL_S):
        return hit.get("url")
    info = _api(
        http,
        {"action": "query", "titles": f"File:{name}", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": WIDTH},
    )
    pages = (info.get("query") or {}).get("pages") or [{}]
    details = (pages[0].get("imageinfo") or [{}])[0]
    url = _larger(details.get("thumburl") or "")
    with _lock:
        _cache[key] = {"url": url, "at": time.time()}
        if url:
            _save()
    return url


def _for_year(http: httpx.Client, title: str, year: int) -> Optional[dict]:
    """The photo of the generation this year falls in, with that generation's years."""
    gens = _generations(http, title)
    earlier = [g for g in gens if g[0] <= year]
    if not earlier:
        return None
    start, anchor, files = max(earlier, key=lambda g: g[0])
    later = sorted(g[0] for g in gens if g[0] > start)
    url = None
    for name in _rank(files)[:2]:
        url = _file_url(http, name)
        if url:
            break
    if not url:
        return None
    return {
        "url": url,
        "title": title,
        "page": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_") + "#" + anchor,
        # the year the next generation starts is the year this one stopped being new
        "years": f"{start}–{later[0] - 1}" if later else f"{start}–",
    }


def _lead(make: str, model: str, http: httpx.Client) -> Optional[dict]:
    """The model's article and its lead photo - the newest generation. None when the
    network failed, which is not remembered: it says nothing about the model."""
    key = _key(make, model)
    with _lock:
        _load()
        hit = _cache.get(key)
    if hit and (hit.get("url") or time.time() - hit.get("at", 0) < MISS_TTL_S):
        return hit

    result: dict = {"url": None}
    try:
        data = _get(http, SEARCH_URL, {"q": f"{make} {model}".strip(), "limit": 5})
    except (_Busy, httpx.HTTPError, ValueError):
        # not remembered: being turned away says nothing about the model
        return None
    page = _choose(data.get("pages", []), make, model)
    url = _larger(((page or {}).get("thumbnail") or {}).get("url", "")) if page else None
    if page and url:
        title = page.get("title") or ""
        result = {
            "url": url,
            "title": title,
            "page": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
        }

    with _lock:
        _cache[key] = {**result, "at": time.time()}
        if result.get("url"):
            _save()
    return result


def find(
    make: str,
    model: str,
    year: Optional[int] = None,
    *,
    client: Optional[httpx.Client] = None,
) -> dict:
    """{url, title, page, years} for a photo of this model - of the generation `year`
    falls in when that can be found, otherwise the article's lead photo. {url: None} when
    there is no photo of this model at all."""
    make, model = (make or "").strip(), (model or "").strip()
    if not settings.catalog_photos or not make:
        return {"url": None}

    own = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": _user_agent()})
    try:
        lead = _lead(make, model, http)
        if not lead or not lead.get("url"):
            return {"url": None}
        if year and lead.get("title"):
            try:
                generation = _for_year(http, lead["title"], int(year))
                if generation:
                    return generation
            except (_Busy, httpx.HTTPError, ValueError, KeyError, IndexError):
                # the lead photo is still a photo of the model; the generation is a
                # refinement, and a refinement that fails is not an answer of "none"
                pass
        return {"url": lead["url"], "title": lead.get("title"), "page": lead.get("page"), "years": None}
    finally:
        if own:
            http.close()


def clear() -> None:
    """For tests."""
    global _loaded
    with _lock:
        _cache.clear()
        _loaded = True
