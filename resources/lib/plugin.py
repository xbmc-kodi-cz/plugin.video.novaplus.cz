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
    menuitems = []

    dur = 0
    title = None
    show_title = None
    aired = None
    video = None

    article_hero = soup.find("div", {"class": "c-hero"})

    try:
        show_title = article_hero.find("h2", {"class": "title"}).find("a").get_text()
        show_url = article_hero.find("h2", {"class": "title"}).find("a")["href"]
        title = article_hero.find("h3", {"class": "subtitle"}).find("a").get_text()
        dur = article_hero.find("time", {"class": "duration"}).get_text()
        aired = article_hero.find("time", {"class": "date"})["datetime"]
        video = article_hero.find("div", {"class": "actions"}).find("a")["href"]

    except:
        pass

    if video:
        if dur:
            dur = get_duration(re.sub(r"[a-z]", ":", (dur.replace(" ", "")))[:-1])
        list_item = xbmcgui.ListItem(
            "[COLOR blue]{0}[/COLOR] · {1}".format(show_title, title)
        )
        list_item.setProperty("IsPlayable", "true")
        list_item.setArt({"thumb": img_res(article_hero.find("img")["data-src"])})

        info = list_item.getVideoInfoTag()

        # info.setPlot(plot)
        # info.setGenre(genre)
        # info.setSeason(season)
        # info.setEpisode(episode)
        info.setTitle(title)
        info.setTvShowTitle(show_title)
        info.setDuration(dur)

        # list_item.setInfo(
        #     "video",
        #     {
        #         "mediatype": "episode",
        #         "tvshowtitle": show_title,
        #         "title": title,
        #         "aired": aired,
        #         "duration": dur,
        #     },
        # )
        listing.append(
            (
                plugin.url_for(get_video, video),
                list_item,
                False,
            )
        )

        menuitems.append(
            (
                _addon.getLocalizedString(30005),
                "Container.Update("
                + plugin.url_for(list_episodes, category="True", show_url=show_url)
                + ")",
            )
        )
        list_item.addContextMenuItems(menuitems)
    articles = soup.find(
        "div",
        {
            "class": "c-article-transformer-carousel swiper-container js-article-transformer-carousel"
        },
    ).find_all("article")
    for article in articles:
        if article["data-tracking-tile-asset"] not in ["article"]:
            menuitems = []

            show_title = article["data-tracking-tile-show-name"]
            title = article["data-tracking-tile-name"]
            dur = article.find("time", {"class": "duration"})
            show_url = article.find("a", {"class": "category"})["href"]

            list_item = xbmcgui.ListItem(
                "[COLOR blue]{0}[/COLOR] · {1}".format(show_title, title)
            )
            menuitems.append(
                (
                    _addon.getLocalizedString(30005),
                    "Container.Update("
                    + plugin.url_for(list_episodes, category="True", show_url=show_url)
                    + ")",
                )
            )
            if dur:
                dur = get_duration(dur.get_text())
            list_item.setInfo(
                "video",
                {
                    "mediatype": "episode",
                    "tvshowtitle": show_title,
                    "title": title,
                    "aired": article.find("time", {"class": "date"})["datetime"],
                    "duration": dur,
                },
            )
            list_item.setArt(
                {
                    "thumb": img_res(
                        article.find("picture").find("source")["data-srcset"]
                    )
                }
            )
            list_item.setProperty("IsPlayable", "true")
            list_item.addContextMenuItems(menuitems)
            listing.append(
                (
                    plugin.url_for(
                        get_video, article.find("a", {"class": "img"})["href"]
                    ),
                    list_item,
                    False,
                )
            )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_episodes/")
def list_episodes():
    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []
    url = plugin.args["show_url"][0]
    category = plugin.args["category"][0]
    if category == "True":
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30007))
        listing.append((plugin.url_for(get_category, show_url=url), list_item, True))
        url = plugin.args["show_url"][0] + "/videa/cele-dily"
    soup = get_page(url)
    try:
        articles = soup.find_all("article", class_="c-article")
        if not articles:
            url = plugin.args["show_url"][0] + "/videa"
            soup = get_page(url)
            articles = soup.find_all("article", class_="c-article")
    except Exception as e:
        xbmcgui.Dialog().notification(
            _addon.getAddonInfo("name"),
            _addon.getLocalizedString(30015),
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )
        return

    count = 0
    show_title = None

    for article in articles:
        if "-voyo" not in article["class"]:
            show_title = article["data-tracking-tile-show-name"]
            title = article["data-tracking-tile-name"]
            dur = article.find("time", {"class": "duration"})
            if dur:
                dur = get_duration(dur.get_text())
            aired = article.find("time", {"class": "date"})["datetime"]

            list_item = xbmcgui.ListItem(title)
            list_item.setInfo(
                "video",
                {
                    "mediatype": "episode",
                    "tvshowtitle": show_title,
                    "title": title,
                    "aired": aired,
                    "duration": dur,
                },
            )
            list_item.setArt(
                {
                    "thumb": img_res(
                        article.find("picture").find("source")["data-srcset"]
                    )
                }
            )
            list_item.setProperty("IsPlayable", "true")
            listing.append(
                (
                    plugin.url_for(
                        get_video, article.find("a", {"class": "img"})["href"]
                    ),
                    list_item,
                    False,
                )
            )
            count += 1
    try:
        next = soup.find("div", {"class": "c-section-cta"})
        if next and count > 0:
            list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
            listing.append(
                (
                    plugin.url_for(
                        list_episodes,
                        category=False,
                        show_url=next.find("button")["data-href"],
                        showtitle=show_title,
                    ),
                    list_item,
                    True,
                )
            )
    except:
        pass

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_latest_videos/")
def list_latest_videos():
    xbmcplugin.setContent(plugin.handle, "episodes")

    listing = []
    menuitems = []

    if not any(arg in plugin.args for arg in ["content", "show_url"]):
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30013))
        listing.append(
            (plugin.url_for(list_latest_videos, content="bonusy"), list_item, True)
        )

        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30014))
        listing.append(
            (plugin.url_for(list_latest_videos, content="ukazky"), list_item, True)
        )

    if "show_url" in plugin.args:
        url = plugin.args["show_url"][0]
    elif "content" in plugin.args:
        url = url = _baseurl + "videa/" + plugin.args["content"][0]
    else:
        url = _baseurl + "videa/cele-dily"

    soup = get_page(url)

    articles = soup.find("div", "js-article-load-more").find_all("article", "c-article")
    count = 0
    show_title = None
    for article in articles:
        if "-voyo" not in article["class"]:
            menuitems = []
            show_title = article["data-tracking-tile-show-name"]
            title = article["data-tracking-tile-name"]
            dur = article.find("time", {"class": "duration"})
            if dur:
                dur = get_duration(dur.get_text())
            aired = article.find("time", {"class": "date"})["datetime"]

            show_url = article.find("div", {"class": "content"}).find("a")["href"]

            list_item = xbmcgui.ListItem(
                "[COLOR blue]{0}[/COLOR] · {1}".format(show_title, title)
            )

            info_tag = list_item.getVideoInfoTag()
            info_tag.setTitle(title)
            info_tag.setTvShowTitle(show_title)
            info_tag.setDuration(dur)
            info_tag.setPremiered(aired)

            list_item.setArt(
                {
                    "thumb": img_res(
                        article.find("picture").find("source")["data-srcset"]
                    )
                }
            )
            list_item.setProperty("IsPlayable", "true")
            listing.append(
                (
                    plugin.url_for(
                        get_video, article.find("a", {"class": "img"})["href"]
                    ),
                    list_item,
                    False,
                )
            )
            menuitems.append(
                (
                    _addon.getLocalizedString(30005),
                    "Container.Update("
                    + plugin.url_for(list_episodes, category="True", show_url=show_url)
                    + ")",
                )
            )
            list_item.addContextMenuItems(menuitems)
            count += 1

    next = soup.find("div", {"class": "c-section-cta"})
    if next and count > 0:
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
        listing.append(
            (
                plugin.url_for(
                    list_latest_videos,
                    show_url=next.find("button")["data-href"],
                    showtitle=show_title,
                ),
                list_item,
                True,
            )
        )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/get_category/")
def get_category():
    listing = []
    soup = get_page(plugin.args["show_url"][0] + "/videa")
    navs = soup.find("nav", "c-tabs")
    if navs:
        for nav in navs.find_all("a"):
            if "/videa" in nav["href"]:
                list_item = xbmcgui.ListItem(nav.get_text())
                listing.append(
                    (
                        plugin.url_for(
                            list_episodes, category="False", show_url=nav["href"]
                        ),
                        list_item,
                        True,
                    )
                )

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


def get_duration(dur):
    duration = 0
    l = dur.strip().split(":")
    for pos, value in enumerate(l[::-1]):
        duration += int(value) * 60**pos
    return duration


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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        },
    )
    if r.status_code == 200:
        return BeautifulSoup(r.content, "html.parser")


@plugin.route("/")
def root():
    listing = []

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30001))
    list_item.setArt({"icon": "DefaultRecentlyAddedEpisodes.png"})
    listing.append((plugin.url_for(list_recent_episodes), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30011))
    list_item.setArt({"icon": "DefaultVideoPlaylists.png"})
    listing.append((plugin.url_for(list_latest_videos), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30003))
    list_item.setArt({"icon": "DefaultTVShows.png"})
    listing.append((plugin.url_for(list_shows_menu), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


def run():
    plugin.run()
