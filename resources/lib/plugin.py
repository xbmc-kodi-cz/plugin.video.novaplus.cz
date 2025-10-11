import routing
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import re
from bs4 import BeautifulSoup
import requests
import inputstreamhelper
import json
from urllib.parse import urljoin

_addon = xbmcaddon.Addon()
plugin = routing.Plugin()
_baseurl = "https://tv.nova.cz/"


@plugin.route("/list_shows/<type>")
def list_shows(type):
    xbmcplugin.setContent(plugin.handle, "tvshows")
    soup = get_page(_baseurl + "porady")
    listing = []
    articles = soup.find_all("div", {"class": "c-show-wrapper"})[int(type)].find_all(
        "a"
    )

    for article in articles:
        title = article["data-tracking-tile-name"]
        list_item = xbmcgui.ListItem(title)

        info = list_item.getVideoInfoTag()
        info.setTitle(title)

        list_item.setArt({"poster": img_res(article.div.img["data-src"])})
        listing.append(
            (
                plugin.url_for(
                    list_episodes,
                    category=True,
                    show_url=article["href"],
                    showtitle=title,
                ),
                list_item,
                True,
            )
        )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_shows_menu/")
def list_shows_menu():
    listing = []
    articles = [
        _addon.getLocalizedString(30002),
        _addon.getLocalizedString(30009),
        _addon.getLocalizedString(30010),
    ]
    for article in articles:
        list_item = xbmcgui.ListItem(article)
        listing.append(
            (plugin.url_for(list_shows, articles.index(article)), list_item, True)
        )
    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_recent_episodes/")
def list_recent_episodes():
    xbmcplugin.setContent(plugin.handle, "episodes")
    soup = get_page(_baseurl)
    listing = []

    article_hero = soup.find("div", {"class": "c-hero"})

    if article_hero and article_hero.get("data-tracking-tile-asset") == "episode":
        show_title = article_hero.find("h2", {"class": "title"}).find("a").get_text()
        show_url = article_hero.find("h2", {"class": "title"}).find("a")["href"]
        title = article_hero.find("h3", {"class": "subtitle"}).find("a").get_text()
        dur = article_hero.find("time", {"class": "duration"}).get_text()
        aired = article_hero.find("time", {"class": "date"})["datetime"]
        video = article_hero.find("div", {"class": "actions"}).find("a")["href"]
        thumb = img_res(article_hero.find("img")["data-src"])

        duration = get_duration(re.sub(r"[a-z]", ":", (dur.replace(" ", "")))[:-1]) if dur else None
        context_menu = [
            (
                _addon.getLocalizedString(30005),
                "Container.Update("
                + plugin.url_for(list_episodes, category="True", show_url=show_url)
                + ")",
            )
        ]

        listing.append(make_video_item(title, show_title, thumb, duration, aired, video, context_menu))

    articles = soup.find(
        "div",
        {"class": "c-article-transformer-carousel swiper-container js-article-transformer-carousel"}
    ).find_all("article")

    for article in articles:
        if article.get("data-tracking-tile-asset") != "episode":
            continue

        show_title = article["data-tracking-tile-show-name"]
        title = article["data-tracking-tile-name"]
        dur_tag = article.find("time", {"class": "duration"})
        dur = get_duration(dur_tag.get_text()) if dur_tag else None
        aired = article.find("time", {"class": "date"})["datetime"]
        video = article.find("a", {"class": "img"})["href"]
        thumb_tag = article.find("picture").find("source") if article.find("picture") else None
        thumb = img_res(thumb_tag["data-srcset"]) if thumb_tag else None

        show_url = article.find("a", {"class": "category"})["href"]
        context_menu = [
            (
                _addon.getLocalizedString(30005),
                "Container.Update(" + plugin.url_for(list_episodes, category="True", show_url=show_url) + ")",
            )
        ]

        listing.append(make_video_item(title, show_title, thumb, dur, aired, video, context_menu))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route("/list_episodes/")
def list_episodes():
    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []
    
    url = plugin.args["show_url"][0]
    category = plugin.args.get("category", ["False"])[0]   

    if category == "True":
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30007))
        listing.append((plugin.url_for(get_category, show_url=url), list_item, True))
        url = f"{url}/videa/cele-dily"
        
    if url.startswith("#"):
        section_id = url[1:]  # bez #
        full_url = plugin.args.get("base_url", [_baseurl])[0] 
    else:
        section_id = None
        full_url = url

    soup = get_page(full_url)
        
    if section_id:
        container = soup.find(id=section_id)
        articles = container.find_all("article", class_="c-article") if container else []
    else:
        articles = soup.find_all("article", class_="c-article")
        if not articles:
            alt_url = f"{url}/videa"
            soup = get_page(alt_url)
            articles = soup.find_all("article", class_="c-article")

    show_title = None
    count = 0
    for article in articles:
        if "-oneplay" in article["class"]:
            continue

        show_title = article.get("data-tracking-tile-show-name")
        title = article.get("data-tracking-tile-name")
        dur_tag = article.find("time", {"class": "duration"})
        dur = get_duration(dur_tag.get_text()) if dur_tag else None
        aired_tag = article.find("time", {"class": "date"})
        aired = aired_tag["datetime"] if aired_tag and aired_tag.has_attr("datetime") else ""

        href = article.find("a", {"class": "img"})["href"]

        thumb_tag = article.find("picture").find("source") if article.find("picture") else None
        thumb = img_res(thumb_tag["data-srcset"]) if thumb_tag else None

        listing.append(make_video_item(title, show_title, thumb, dur, aired, href))
        count += 1

    all_videos_div = soup.find("div", {"class": "c-section-actions -bottom"})
    if section_id == "all":
        if all_videos_div:
            a_tag = all_videos_div.find("a", {"href": True})
            if a_tag:
                url_page2 = a_tag["href"].rstrip("/") + "/strana-2"
                list_item_page2 = xbmcgui.ListItem(_addon.getLocalizedString(30004))
                listing.append(
                    (
                        plugin.url_for(list_episodes, show_url=url_page2, showtitle=show_title),
                        list_item_page2,
                        True,
                    )
                )
            
    next_div = soup.find("div", {"class": "c-section-cta"})
    if next_div and count > 0:
        btn = next_div.find("button")
        if btn and btn.has_attr("data-href"):
            list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
            listing.append(
                (
                    plugin.url_for(
                        list_episodes,
                        category="False",
                        show_url=btn["data-href"],
                        showtitle=show_title,
                    ),
                    list_item,
                    True,
                )
            )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)



@plugin.route("/list_latest_videos/")
def list_latest_videos():
    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []

    if "show_url" in plugin.args:
        url = plugin.args["show_url"][0]
    elif "content" in plugin.args:
        url = _baseurl + "videa/" + plugin.args["content"][0]
    else:
        url = _baseurl + "videa/cele-dily"

    soup = get_page(url)

    articles_container = soup.find("div", "js-article-load-more")
    if not articles_container:
        xbmcplugin.endOfDirectory(plugin.handle)
        return

    articles = articles_container.find_all("article", "c-article")
    show_title = None
    count = 0

    for article in articles:
        if "-oneplay" in article["class"]:
            continue

        show_title = article["data-tracking-tile-show-name"]
        title = article["data-tracking-tile-name"]
        dur_tag = article.find("time", {"class": "duration"})
        dur = get_duration(dur_tag.get_text()) if dur_tag else None
        aired = article.find("time", {"class": "date"})["datetime"]
        video_url = article.find("a", {"class": "img"})["href"]
        thumb_tag = article.find("picture").find("source") if article.find("picture") else None
        thumb = img_res(thumb_tag["data-srcset"]) if thumb_tag else None

        show_url = article.find("div", {"class": "content"}).find("a")["href"]
        context_menu = [
            (
                _addon.getLocalizedString(30005),
                "Container.Update(" + plugin.url_for(list_episodes, category="True", show_url=show_url) + ")",
            )
        ]

        listing.append(make_video_item(title, show_title, thumb, dur, aired, video_url, context_menu))
        count += 1

    next_div = soup.find("div", {"class": "c-section-cta"})
    if next_div and count > 0:
        btn = next_div.find("button")
        if btn and btn.has_attr("data-href"):
            list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
            listing.append(
                (
                    plugin.url_for(list_latest_videos, show_url=btn["data-href"], show_title=show_title),
                    list_item,
                    True,
                )
            )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/get_category/")
def get_category():
    listing = []
    base_url = plugin.args["show_url"][0]
    soup = get_page(base_url)

    navs = soup.find("nav", class_="c-tabs")
    if not navs:
        xbmcplugin.endOfDirectory(plugin.handle)
        return

    for nav in navs.find_all("a"):
        href = nav.get("href")
        text = nav.get_text(strip=True)
        if not href or not ("videa" in href or href.startswith("#")):
            continue

        show_url = href if href.startswith(("http", "#")) else urljoin(base_url, href)

        list_item = xbmcgui.ListItem(text)
        item_url = plugin.url_for(
            list_episodes,
            category="False",
            show_url=show_url,
            base_url=base_url if href.startswith("#") else None,
        )
        listing.append((item_url, list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/get_video/<path:url>")
def get_video(url):
    PROTOCOL = "mpd"
    DRM = "com.widevine.alpha"
    soup = get_page(url)

    drm = None
    drm_server = None
    drm_token = None

    json_stream = json.loads(
        soup.find(
            "script", type="application/ld+json", text=re.compile(r"embedUrl")
        ).string
    )

    if "video" in json_stream:
        embeded_url = json_stream["video"]["embedUrl"]
    elif "embedUrl" in json_stream:
        embeded_url = json_stream["embedUrl"]
    else:
        pass

    embeded = get_page(embeded_url)

    try:
        json_data = json.loads(
            re.compile('{"tracks":(.+?),"duration"').findall(str(embeded))[0]
        )
        stream_data = json_data["DASH"][0]
        try:
            drm = stream_data["drm"][1]
            drm_server = drm["serverURL"]
            drm_token = drm["headers"][0]["value"]
        except:
            pass
    except:
        json_data = json.loads(
            json.dumps(re.compile("player: (.+)").findall(str(embeded)))
        )
        stream_data = json.loads(json_data[0])["lib"]["source"]["sources"][1]
        try:
            drm = stream_data["contentProtection"]
            drm_server = drm["widevine"]["licenseAcquisitionURL"]
            drm_token = drm["token"]
        except:
            pass

    if stream_data:
        list_item = xbmcgui.ListItem()
        
        is_helper = inputstreamhelper.Helper(PROTOCOL, drm=DRM)
        if is_helper.check_inputstream():
            list_item.setPath(stream_data["src"])
            list_item.setContentLookup(False)
            list_item.setMimeType("application/xml+dash")
            list_item.setProperty("inputstream", "inputstream.adaptive")
            if drm_server:
                list_item.setProperty("inputstream.adaptive.license_type", DRM)
                list_item.setProperty("inputstream.adaptive.manifest_type", "DASH")
                list_item.setProperty(
                    "inputstream.adaptive.license_key",
                    drm_server + "|" + "X-AxDRM-Message=" + drm_token + "|R{SSM}|",
                )
        xbmcplugin.setResolvedUrl(plugin.handle, True, list_item)
    else:
        xbmcgui.Dialog().notification(
            _addon.getAddonInfo("name"),
            _addon.getLocalizedString(30006),
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )

def make_video_item(title, show_title=None, thumb=None, duration=None, aired=None, url=None, context_menu=None):
    list_item = xbmcgui.ListItem(title if not show_title else f"[COLOR blue]{show_title}[/COLOR] · {title}")
    list_item.setProperty("IsPlayable", "true")
       
    info = list_item.getVideoInfoTag()
    info.setTitle(title)
    if show_title:
        info.setMediaType("episode")
        info.setTvShowTitle(show_title)
    if duration:
        info.setDuration(duration)
    if aired:
        info.setPremiered(aired)
        
    if thumb:
        list_item.setArt({"thumb": thumb})
    
    if context_menu:
        list_item.addContextMenuItems(context_menu)
    
    if url:
        return plugin.url_for(get_video, url), list_item, False
    return list_item

def get_duration(dur):
    if not dur:
        return 0
    dur = dur.lower().replace(" ", "")
    dur = re.sub(r"[^0-9:]", ":", dur)
    parts = [int(x) for x in dur.split(":") if x.isdigit()]
    return sum(val * (60 ** i) for i, val in enumerate(reversed(parts)))


def img_res(url):
    dimensions_mapping = {
        "314x175": "942x525",
        "275x153": "825x459",
        "276x383": "828x1149",
    }

    for old_dim, new_dim in dimensions_mapping.items():
        if old_dim in url:
            return url.replace(old_dim, new_dim)

    return url


def get_page(url):
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        },
    )
    if r.status_code == 200:
        return BeautifulSoup(r.content, "html.parser")


@plugin.route("/")
def root():
    menu = [
        (_addon.getLocalizedString(30001), list_recent_episodes, "DefaultRecentlyAddedEpisodes.png"),
        (_addon.getLocalizedString(30011), list_latest_videos, "DefaultVideoPlaylists.png"),
        (_addon.getLocalizedString(30003), list_shows_menu, "DefaultTVShows.png"),
    ]
    listing = []
    for name, fnc, icon in menu:
        list_item = xbmcgui.ListItem(name)
        if icon:
            list_item.setArt({"icon": icon})
        listing.append((plugin.url_for(fnc), list_item, True))
    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


def run():
    plugin.run()
