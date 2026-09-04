# -*- coding: utf-8 -*-
"""Kodi video addon for the free catalogue on tv.nova.cz."""

import json
import re
import traceback
from functools import wraps
from urllib.parse import urljoin

import inputstreamhelper
import requests
import routing
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
from bs4 import BeautifulSoup

_addon = xbmcaddon.Addon()
plugin = routing.Plugin()

_baseurl = "https://tv.nova.cz/"
_useragent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
_timeout = (10, 30)
_drm = "com.widevine.alpha"

_session = requests.Session()
_session.headers.update({"User-Agent": _useragent})


class NovaError(Exception):
    """Failure worth reporting to the user, carrying the string id to show."""

    def __init__(self, string_id=30016):
        super().__init__(_addon.getLocalizedString(string_id))
        self.string_id = string_id


def log(message, level=xbmc.LOGDEBUG):
    xbmc.log("[{}] {}".format(_addon.getAddonInfo("id"), message), level)


def notify(string_id):
    xbmcgui.Dialog().notification(
        _addon.getAddonInfo("name"),
        _addon.getLocalizedString(string_id),
        xbmcgui.NOTIFICATION_ERROR,
        5000,
    )


def guard(playable=False):
    """Turn a scraping failure into a notification instead of a Kodi error dialog."""

    def decorator(fnc):
        @wraps(fnc)
        def wrapper(*args, **kwargs):
            try:
                return fnc(*args, **kwargs)
            except NovaError as exc:
                log("{}: {}".format(fnc.__name__, exc), xbmc.LOGERROR)
                string_id = exc.string_id
            except Exception:
                log(
                    "{} failed:\n{}".format(fnc.__name__, traceback.format_exc()),
                    xbmc.LOGERROR,
                )
                string_id = 30017
            notify(string_id)
            if playable:
                xbmcplugin.setResolvedUrl(plugin.handle, False, xbmcgui.ListItem())
            else:
                xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)

        return wrapper

    return decorator


def _fetch(url, params=None):
    log("GET " + url)
    try:
        response = _session.get(url, params=params, timeout=_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NovaError(30016) from exc
    return response


def get_page(url):
    return BeautifulSoup(_fetch(url).content, "html.parser")


def get_source(url):
    return _fetch(url).text


def get_json(url, params=None):
    try:
        return _fetch(url, params).json()
    except ValueError as exc:
        raise NovaError(30016) from exc


def _classes(tag):
    value = tag.get("class")
    if not value:
        return set()
    return set(value.split()) if isinstance(value, str) else set(value)


def find_tag(node, name, *classes):
    """First `name` tag carrying all of `classes`, whatever their order."""
    wanted = set(classes)
    return node.find(lambda tag: tag.name == name and wanted <= _classes(tag))


def find_tags(node, name, *classes):
    wanted = set(classes)
    return node.find_all(lambda tag: tag.name == name and wanted <= _classes(tag))


_ISO_DURATION = re.compile(r"(\d+)\s*([HMS])")
_UNIT_DURATION = re.compile(r"(\d+)\s*(min|[hms])")
_UNIT_SECONDS = {"h": 3600, "m": 60, "min": 60, "s": 1}


def parse_duration(text):
    """Seconds from "2m 29s", "45 min" or "01:02:03"."""
    if not text:
        return 0
    parts = _UNIT_DURATION.findall(text.strip().lower())
    if parts:
        return sum(int(value) * _UNIT_SECONDS[unit] for value, unit in parts)
    numbers = [int(number) for number in re.findall(r"\d+", text)]
    return sum(value * 60 ** index for index, value in enumerate(reversed(numbers)))


def get_duration(tag):
    """Seconds from <time class="duration" datetime="PT 01H 02M 03S">1:02:03</time>.

    The datetime attribute is unambiguous, the text is not ("45 min" vs "45:00").
    """
    if tag is None:
        return 0
    iso = (tag.get("datetime") or "").upper().lstrip()
    if iso.startswith("PT"):
        seconds = sum(
            int(value) * _UNIT_SECONDS[unit.lower()]
            for value, unit in _ISO_DURATION.findall(iso)
        )
        if seconds:
            return seconds
    return parse_duration(tag.get_text())


_IMAGE_SIZE = re.compile(r"/r(\d+)x(\d+)(n?)/")
_IMAGE_SCALE = 3
_IMAGE_SMALL = 400


def img_res(url):
    """Ask the image CDN for a bigger rendition of the small web page thumbnails.

    Renditions already sized for a big screen (posters, hero images) are left
    alone, upscaling those only costs bandwidth.
    """

    def upscale(match):
        width, height, retina = int(match.group(1)), int(match.group(2)), match.group(3)
        if width >= _IMAGE_SMALL:
            return match.group(0)
        return "/r{}x{}{}/".format(width * _IMAGE_SCALE, height * _IMAGE_SCALE, retina)

    return _IMAGE_SIZE.sub(upscale, url, count=1)


def first_url(srcset):
    """A srcset may list several candidates with descriptors, take the first URL."""
    if not srcset:
        return None
    return srcset.split(",")[0].strip().split(" ")[0] or None


def get_image(node):
    """Best image URL inside a tile."""
    if node is None:
        return None
    sources = node.find_all("source")
    if sources:
        # A <source> carrying a media query is the small mobile variant.
        source = next((item for item in sources if not item.get("media")), sources[-1])
        url = first_url(source.get("data-srcset") or source.get("srcset"))
        if url:
            return img_res(url)
    image = node.find("img")
    if image is not None:
        # src holds a placeholder until lazyload swaps in data-src.
        url = image.get("data-src") or image.get("src")
        if url:
            return img_res(url)
    return None


def parse_article(article):
    """Fields of an <article class="c-article"> video tile, or None if unusable."""
    link = find_tag(article, "a", "img") or article.find("a", href=True)
    if link is None or not link.get("href"):
        return None
    title = article.get("data-tracking-tile-name")
    if not title:
        heading = find_tag(article, "h3", "title")
        title = heading.get_text(strip=True) if heading is not None else None
    if not title:
        return None
    date = find_tag(article, "time", "date")
    show_link = find_tag(article, "a", "category")
    return {
        "url": link["href"],
        "title": title,
        "show_title": article.get("data-tracking-tile-show-name"),
        "show_url": show_link["href"] if show_link is not None else None,
        "duration": get_duration(find_tag(article, "time", "duration")),
        "aired": date.get("datetime") if date is not None else None,
        "thumb": get_image(article),
    }


def parse_hero(hero):
    """The featured video on the homepage, but only when it is a full episode."""
    if hero is None:
        return None
    actions = find_tag(hero, "div", "actions")
    play_link = actions.find("a", href=True) if actions is not None else None
    if play_link is None or "/video-epizoda/" not in play_link["href"]:
        return None
    show_heading = find_tag(hero, "h2", "title")
    show_link = show_heading.find("a", href=True) if show_heading is not None else None
    subtitle = find_tag(hero, "h3", "subtitle")
    date = find_tag(hero, "time", "date")
    return {
        "url": play_link["href"],
        "title": subtitle.get_text(strip=True) if subtitle is not None else None,
        "show_title": show_link.get_text(strip=True) if show_link is not None else None,
        "show_url": show_link["href"] if show_link is not None else None,
        "duration": get_duration(find_tag(hero, "time", "duration")),
        "aired": date.get("datetime") if date is not None else None,
        "thumb": get_image(hero),
    }


def video_item(entry, show_prefix=True):
    """A playable directory tuple for a parsed video entry.

    Mixed listings prefix the label with the show, listings that already sit
    inside a show do not.
    """
    title = entry["title"]
    show_title = entry.get("show_title")
    label = (
        "[COLOR blue]{}[/COLOR] • {}".format(show_title, title)
        if show_title and show_prefix
        else title
    )
    list_item = xbmcgui.ListItem(label)
    list_item.setProperty("IsPlayable", "true")

    info = list_item.getVideoInfoTag()
    # For video content Kodi rebuilds the list label out of the info tag, so the
    # show has to be part of the title itself, not just of the ListItem label.
    info.setTitle(label)
    if show_title:
        info.setMediaType("episode")
        info.setTvShowTitle(show_title)
    if entry.get("duration"):
        info.setDuration(entry["duration"])
    if entry.get("aired"):
        info.setPremiered(entry["aired"])
    if entry.get("thumb"):
        list_item.setArt({"thumb": entry["thumb"]})
    if entry.get("show_url"):
        list_item.addContextMenuItems(
            [
                (
                    _addon.getLocalizedString(30005),
                    "Container.Update({})".format(
                        plugin.url_for(
                            list_episodes, category="True", show_url=entry["show_url"]
                        )
                    ),
                )
            ]
        )
    return plugin.url_for(get_video, entry["url"]), list_item, False


def add_directory(listing, sort_methods=()):
    for method in sort_methods:
        xbmcplugin.addSortMethod(plugin.handle, method)
    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


_EPISODE_SORT = (
    xbmcplugin.SORT_METHOD_UNSORTED,
    xbmcplugin.SORT_METHOD_LABEL,
    xbmcplugin.SORT_METHOD_DURATION,
)
_SHOW_SORT = (
    xbmcplugin.SORT_METHOD_UNSORTED,
    xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE,
)


def show_sections(soup):
    """Genre carousels on /porady, in page order."""
    sections = []
    for section in find_tags(soup, "section", "minor-inner", "-shows"):
        heading = find_tag(section, "h2", "c-title")
        if heading is None:
            continue
        shows = []
        for link in find_tags(section, "a", "-show-slide"):
            href = link.get("href")
            image = link.find("img")
            title = (image.get("alt") if image is not None else None) or link.get_text(
                strip=True
            )
            if href and title:
                shows.append({"title": title, "url": href, "poster": get_image(link)})
        if shows:
            sections.append({"title": heading.get_text(strip=True), "shows": shows})
    return sections


def alphabetical_shows(soup):
    """The full A-Z list at the bottom of /porady."""
    wrapper = find_tag(soup, "div", "c-show-wrapper")
    shows = []
    if wrapper is None:
        return shows
    for link in find_tags(wrapper, "a", "c-show"):
        href = link.get("href")
        title = link.get("data-tracking-tile-name")
        if not title:
            heading = find_tag(link, "h3", "title")
            title = heading.get_text(strip=True) if heading is not None else None
        if href and title:
            shows.append({"title": title, "url": href, "poster": get_image(link)})
    return shows


@plugin.route("/list_shows_menu/")
@guard()
def list_shows_menu():
    soup = get_page(urljoin(_baseurl, "porady"))
    listing = []
    for index, section in enumerate(show_sections(soup)):
        list_item = xbmcgui.ListItem(section["title"])
        list_item.setArt({"icon": "DefaultTVShows.png"})
        listing.append((plugin.url_for(list_shows, str(index)), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30010))
    list_item.setArt({"icon": "DefaultTVShows.png"})
    listing.append((plugin.url_for(list_shows, "az"), list_item, True))
    add_directory(listing)


@plugin.route("/list_shows/<section>")
@guard()
def list_shows(section):
    xbmcplugin.setContent(plugin.handle, "tvshows")
    soup = get_page(urljoin(_baseurl, "porady"))

    if section == "az":
        title = _addon.getLocalizedString(30010)
        shows = alphabetical_shows(soup)
    else:
        sections = show_sections(soup)
        try:
            chosen = sections[int(section)]
        except (ValueError, IndexError):
            raise NovaError(30015) from None
        title, shows = chosen["title"], chosen["shows"]

    if not shows:
        raise NovaError(30015)

    xbmcplugin.setPluginCategory(plugin.handle, title)
    listing = []
    for show in shows:
        list_item = xbmcgui.ListItem(show["title"])
        info = list_item.getVideoInfoTag()
        info.setMediaType("tvshow")
        info.setTitle(show["title"])
        info.setTvShowTitle(show["title"])
        if show["poster"]:
            list_item.setArt({"poster": show["poster"], "thumb": show["poster"]})
        listing.append(
            (
                plugin.url_for(list_episodes, category="True", show_url=show["url"]),
                list_item,
                True,
            )
        )
    add_directory(listing, _SHOW_SORT)


@plugin.route("/list_recent_episodes/")
@guard()
def list_recent_episodes():
    xbmcplugin.setContent(plugin.handle, "episodes")
    soup = get_page(_baseurl)
    listing = []

    hero = parse_hero(find_tag(soup, "div", "c-hero"))
    if hero and hero["title"]:
        listing.append(video_item(hero))

    carousel = find_tag(soup, "div", "js-article-transformer-carousel")
    for article in find_tags(carousel, "article", "c-article") if carousel else []:
        if "-oneplay" in _classes(article):
            continue
        if article.get("data-tracking-tile-asset") != "episode":
            continue
        entry = parse_article(article)
        if entry:
            listing.append(video_item(entry))

    add_directory(listing, _EPISODE_SORT)


@plugin.route("/list_episodes/")
@guard()
def list_episodes():
    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []

    url = plugin.args.get("show_url", [None])[0]
    if not url:
        raise NovaError(30015)
    category = plugin.args.get("category", ["False"])[0]

    fallback_url = None
    if category == "True":
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30007))
        list_item.setArt({"icon": "DefaultFolder.png"})
        listing.append((plugin.url_for(get_category, show_url=url), list_item, True))
        # Shows without free full episodes have an empty /videa/cele-dily page,
        # so fall back to all of their videos.
        fallback_url = "{}/videa".format(url.rstrip("/"))
        url = "{}/videa/cele-dily".format(url.rstrip("/"))

    if url.startswith("#"):
        # A tab of the show page, its videos are already in the document we fetch.
        section_id = url[1:]
        full_url = plugin.args.get("base_url", [_baseurl])[0]
    else:
        section_id = None
        full_url = url

    soup = get_page(full_url)

    if section_id:
        container = soup.find(id=section_id)
    else:
        container = soup
        if not find_tags(soup, "article", "c-article") and fallback_url:
            soup = container = get_page(fallback_url)

    entries, next_url = collect_videos(container)

    show_title = None
    for entry in entries:
        show_title = entry["show_title"] or show_title
        # The show is the parent folder here, so neither the label nor a
        # "go to show" context entry needs to name it again.
        entry["show_url"] = None
        listing.append(video_item(entry, show_prefix=False))

    if show_title:
        xbmcplugin.setPluginCategory(plugin.handle, show_title)
    if not entries:
        notify(30018)

    if section_id == "all":
        actions = find_tag(soup, "div", "c-section-actions", "-bottom")
        link = actions.find("a", href=True) if actions is not None else None
        if link is not None:
            list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
            listing.append(
                (
                    plugin.url_for(
                        list_episodes, show_url=link["href"].rstrip("/") + "/strana-2"
                    ),
                    list_item,
                    True,
                )
            )

    if next_url:
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
        listing.append(
            (
                plugin.url_for(list_episodes, category="False", show_url=next_url),
                list_item,
                True,
            )
        )

    add_directory(listing, _EPISODE_SORT)


@plugin.route("/list_latest_videos/")
@guard()
def list_latest_videos():
    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []

    if "show_url" in plugin.args:
        url = plugin.args["show_url"][0]
    elif "content" in plugin.args:
        url = urljoin(_baseurl, "videa/" + plugin.args["content"][0])
    else:
        url = urljoin(_baseurl, "videa/cele-dily")

    soup = get_page(url)
    container = find_tag(soup, "div", "js-article-load-more")
    if container is None:
        raise NovaError(30015)

    entries, next_url = collect_videos(container)
    for entry in entries:
        listing.append(video_item(entry))
    if not entries:
        notify(30018)

    if next_url:
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
        listing.append(
            (plugin.url_for(list_latest_videos, show_url=next_url), list_item, True)
        )

    add_directory(listing, _EPISODE_SORT)


def load_more_url(soup):
    """The "load more" button points at an endpoint serving the next page fragment."""
    section = find_tag(soup, "div", "c-section-cta")
    button = section.find("button", attrs={"data-href": True}) if section else None
    return button["data-href"] if button is not None else None


def free_videos(node):
    """Parsed video tiles under `node`, minus the ones needing an Oneplay account."""
    entries = []
    for article in find_tags(node, "article", "c-article"):
        if "-oneplay" in _classes(article):
            continue
        entry = parse_article(article)
        if entry:
            entries.append(entry)
    return entries


_TARGET_ITEMS = 20
_MAX_REQUESTS = 5
_MAX_EMPTY_PAGES = 2


def collect_videos(node):
    """Videos for one listing, plus the URL of the next one or None.

    A server-rendered page holds only a handful of tiles and the browser pulls
    the rest through the "load more" endpoint, so several of those are merged
    into a single Kodi page. Older parts of an archive tend to sit entirely
    behind the Oneplay paywall: once a couple of pages in a row yield nothing
    playable, the free content has run out and no "next" item is offered.
    """
    entries = free_videos(node)
    empty_pages = 0 if entries else 1
    requests_made = 1
    next_url = load_more_url(node)

    while (
        next_url
        and len(entries) < _TARGET_ITEMS
        and requests_made < _MAX_REQUESTS
        and empty_pages < _MAX_EMPTY_PAGES
    ):
        soup = get_page(next_url)
        requests_made += 1
        found = free_videos(soup)
        empty_pages = 0 if found else empty_pages + 1
        entries.extend(found)
        next_url = load_more_url(soup)

    return entries, next_url if empty_pages == 0 else None


@plugin.route("/get_category/")
@guard()
def get_category():
    listing = []
    base_url = plugin.args.get("show_url", [None])[0]
    if not base_url:
        raise NovaError(30015)

    soup = get_page(base_url)
    tabs = find_tag(soup, "nav", "c-tabs")
    if tabs is None:
        raise NovaError(30015)

    for link in tabs.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True)
        if not text or not ("videa" in href or href.startswith("#")):
            continue

        list_item = xbmcgui.ListItem(text)
        list_item.setArt({"icon": "DefaultFolder.png"})
        if href.startswith("#"):
            item_url = plugin.url_for(
                list_episodes, category="False", show_url=href, base_url=base_url
            )
        else:
            item_url = plugin.url_for(
                list_episodes, category="False", show_url=urljoin(base_url, href)
            )
        listing.append((item_url, list_item, True))

    add_directory(listing)


_PLAYER_CONFIG = re.compile(r"player:\s*(\{.+\})\s*$", re.MULTILINE)
_LD_JSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)


def plain_text(html):
    """Readable text out of a JSON-LD description.

    Nova appends cross-promotional paragraphs ("watch the premiere on Oneplay")
    to a lot of them. Those are wrapped links and only clutter the player, so
    paragraphs containing a link are dropped as long as something remains.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    paragraphs = soup.find_all("p")
    if paragraphs:
        wanted = [p for p in paragraphs if p.find("a") is None] or paragraphs
        text = "\n".join(p.get_text(" ", strip=True) for p in wanted)
    else:
        text = soup.get_text(" ", strip=True)
    return text.strip() or None


def video_metadata(page_source):
    """Embed URL and the descriptive fields of a video, from its JSON-LD block.

    Read straight out of the markup: a video page is a few hundred kilobytes
    and there is no reason to build a parse tree for one script tag.
    """
    for block in _LD_JSON.findall(page_source):
        if "embedUrl" not in block:
            continue
        try:
            data = json.loads(block)
        except ValueError:
            continue
        # An episode page nests the VideoObject, a standalone video is one.
        video = data["video"] if isinstance(data.get("video"), dict) else data
        embed_url = video.get("embedUrl") or data.get("embedUrl")
        if not embed_url:
            continue
        series = data.get("partOfSeries")
        return {
            "embed_url": embed_url,
            "title": data.get("name") or video.get("name"),
            "plot": plain_text(data.get("description") or video.get("description")),
            "show_title": series.get("name") if isinstance(series, dict) else None,
            "aired": (video.get("uploadDate") or "")[:10] or None,
            "thumb": video.get("thumbnailUrl") or data.get("thumbnailUrl"),
        }
    raise NovaError(30006)


def get_player_config(page_source):
    """window.PageData.player from the embed page."""
    match = _PLAYER_CONFIG.search(page_source)
    if match is None:
        raise NovaError(30006)
    try:
        return json.loads(match.group(1))
    except ValueError as exc:
        raise NovaError(30006) from exc


def dash_source(player):
    """The MPEG-DASH entry among the player sources, whatever its position."""
    try:
        sources = player["lib"]["source"]["sources"]
    except (KeyError, TypeError):
        return None
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        if source.get("type") == "application/dash+xml" or ".mpd" in (
            source.get("src") or ""
        ):
            return source
    return None


def license_info(source):
    """(license URL, token) for a Widevine protected source, or (None, None)."""
    protection = source.get("contentProtection") or {}
    widevine = protection.get("widevine") or {}
    return widevine.get("licenseAcquisitionURL"), protection.get("token")


def text_tracks(player):
    try:
        return player["lib"]["source"].get("textTracks") or []
    except (KeyError, TypeError):
        return []


@plugin.route("/get_video/<path:url>")
@guard(playable=True)
def get_video(url):
    meta = video_metadata(get_source(url))
    player = get_player_config(get_source(meta["embed_url"]))

    source = dash_source(player)
    if source is None or not source.get("src"):
        raise NovaError(30006)

    license_url, token = license_info(source)
    helper = inputstreamhelper.Helper("mpd", drm=_drm if license_url else None)
    if not helper.check_inputstream():
        raise NovaError(30006)

    list_item = xbmcgui.ListItem(meta["title"] or "", path=source["src"])
    list_item.setContentLookup(False)
    list_item.setMimeType("application/dash+xml")
    list_item.setProperty("inputstream", "inputstream.adaptive")
    list_item.setProperty("inputstream.adaptive.manifest_type", "mpd")
    if license_url:
        list_item.setProperty("inputstream.adaptive.license_type", _drm)
        list_item.setProperty(
            "inputstream.adaptive.license_key",
            "{}|X-AxDRM-Message={}|R{{SSM}}|".format(license_url, token or ""),
        )

    subtitles = [
        track["src"]
        for track in text_tracks(player)
        if isinstance(track, dict) and track.get("src")
    ]
    if subtitles:
        list_item.setSubtitles(subtitles)

    if meta["thumb"]:
        list_item.setArt({"thumb": meta["thumb"]})

    info = list_item.getVideoInfoTag()
    if meta["title"]:
        info.setTitle(meta["title"])
    if meta["plot"]:
        info.setPlot(meta["plot"])
    if meta["show_title"]:
        info.setMediaType("episode")
        info.setTvShowTitle(meta["show_title"])
    if meta["aired"]:
        info.setPremiered(meta["aired"])
    duration = (player.get("sourceInfo") or {}).get("duration")
    if duration:
        info.setDuration(int(duration))

    xbmcplugin.setResolvedUrl(plugin.handle, True, list_item)


# The site's own search box talks to this endpoint, so search needs no scraping.
_SEARCH_API = urljoin(_baseurl, "api/v1/ela/search")
_SEARCH_CONTENT_ID = "33160"
_IMAGE_PLACEHOLDER = re.compile(r"\{WIDTH\}x\{HEIGHT\}")
_CZECH_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def search_image(url, width, height):
    """Search results carry a templated image URL to be filled with a size."""
    return _IMAGE_PLACEHOLDER.sub("{}x{}".format(width, height), url) if url else None


def iso_date(text):
    """"04.09.2026" as the ISO date Kodi expects, or None."""
    match = _CZECH_DATE.match(text or "")
    if match is None:
        return None
    day, month, year = match.groups()
    return "{}-{}-{}".format(year, month, day)


def search_group(payload, group_type):
    for group in payload.get("resultGroups") or []:
        if group.get("type") == group_type:
            return group
    return {}


def search_items(payload, group_type):
    """Real results of one group, without the ad snippets mixed into them."""
    return [
        item
        for item in search_group(payload, group_type).get("data") or []
        if str(item.get("entity") or "").startswith("onair.")
        and (item.get("content") or {}).get("link")
        and (item.get("content") or {}).get("title")
    ]


@plugin.route("/search/")
@guard()
def search():
    query = plugin.args.get("query", [None])[0]
    page_url = plugin.args.get("page", [None])[0]

    if not page_url and not query:
        query = xbmcgui.Dialog().input(_addon.getLocalizedString(30019))
        if not query:
            xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)
            return

    if page_url:
        payload = get_json(page_url)
    else:
        payload = get_json(
            _SEARCH_API,
            {"query": query, "offset": 0, "contentId": _SEARCH_CONTENT_ID},
        )

    xbmcplugin.setContent(plugin.handle, "videos")
    if query:
        xbmcplugin.setPluginCategory(plugin.handle, query)
    listing = []

    for item in search_items(payload, "novaShow"):
        content = item["content"]
        list_item = xbmcgui.ListItem(content["title"])
        info = list_item.getVideoInfoTag()
        info.setMediaType("tvshow")
        info.setTitle(content["title"])
        info.setTvShowTitle(content["title"])
        poster = search_image(content.get("image"), 828, 1149)
        if poster:
            list_item.setArt({"poster": poster, "thumb": poster})
        listing.append(
            (
                plugin.url_for(
                    list_episodes, category="True", show_url=content["link"]
                ),
                list_item,
                True,
            )
        )

    for item in search_items(payload, "novaVideo"):
        content = item["content"]
        listing.append(
            video_item(
                {
                    "url": content["link"],
                    "title": content["title"],
                    "show_title": content.get("show"),
                    "show_url": content.get("linkShow"),
                    "duration": parse_duration(content.get("length")),
                    "aired": iso_date(content.get("airedAt")),
                    "thumb": search_image(content.get("image"), 942, 525),
                }
            )
        )

    if not listing:
        notify(30018)

    next_page = (search_group(payload, "novaVideo").get("nextPage") or {}).get("url")
    if next_page:
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
        listing.append((plugin.url_for(search, page=next_page), list_item, True))

    add_directory(listing)


@plugin.route("/")
@guard()
def root():
    menu = [
        (
            _addon.getLocalizedString(30001),
            list_recent_episodes,
            "DefaultRecentlyAddedEpisodes.png",
        ),
        (
            _addon.getLocalizedString(30011),
            list_latest_videos,
            "DefaultVideoPlaylists.png",
        ),
        (_addon.getLocalizedString(30003), list_shows_menu, "DefaultTVShows.png"),
        (_addon.getLocalizedString(30019), search, "DefaultAddonsSearch.png"),
    ]
    listing = []
    for name, fnc, icon in menu:
        list_item = xbmcgui.ListItem(name)
        list_item.setArt({"icon": icon})
        listing.append((plugin.url_for(fnc), list_item, True))
    add_directory(listing)


def run():
    plugin.run()
