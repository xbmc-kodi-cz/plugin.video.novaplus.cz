# -*- coding: utf-8 -*-
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

_baseurl = 'https://tv.nova.cz/'


@plugin.route('/list_shows/<type>')
def list_shows(type):
    xbmcplugin.setContent(plugin.handle, 'tvshows')
    soup = get_page(_baseurl+'porady')
    listing = []
    articles = soup.find_all(
        'div', {'class': 'c-show-wrapper'})[int(type)].find_all('a')

    for article in articles:
        title = article['data-tracking-tile-name']
        list_item = xbmcgui.ListItem(title)
        list_item.setInfo('video', {'mediatype': 'tvshow', 'title': title})
        list_item.setArt({'poster': img_res(article.div.img['data-src'])})
        listing.append(
            (plugin.url_for(get_list, category=True, show_url=article['href'], showtitle=title), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route('/list_shows_menu/')
def list_shows_menu():
    listing = []
    articles = [_addon.getLocalizedString(30002), _addon.getLocalizedString(
        30009), _addon.getLocalizedString(30010)]
    for article in articles:
        list_item = xbmcgui.ListItem(article)
        listing.append(
            (plugin.url_for(list_shows, articles.index(article)), list_item, True))
    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@ plugin.route('/list_recent/')
def list_recent():
    xbmcplugin.setContent(plugin.handle, 'episodes')
    soup = get_page(_baseurl)
    listing = []
    articles = soup.find('div', {'class': 'c-article-transformer-carousel swiper-container js-article-transformer-carousel'}
                         ).find_all('article')
    for article in articles:
        menuitems = []

        show_title = article['data-tracking-tile-show-name']
        title = article['data-tracking-tile-name']

        list_item = xbmcgui.ListItem(
            u'[COLOR blue]{0}[/COLOR] · {1}'.format(show_title, title))
        dur = article.find('time', {'class': 'duration'})
        show_url = article.find('a', {'class': 'category'})['href']
        menuitems.append((_addon.getLocalizedString(30005), 'Container.Update(' +
                         plugin.url_for(get_list, category='True', show_url=show_url)+')'))
        if dur:
            dur = get_duration(dur.get_text())
        list_item.setInfo(
            'video', {'mediatype': 'episode', 'tvshowtitle': show_title, 'title': title, 'aired': article.find('time', {'class': 'date'})['datetime'], 'duration': dur})
        list_item.setArt({'icon': img_res(article.find(
            'picture').find('source')['data-srcset'])})
        list_item.setProperty('IsPlayable', 'true')
        list_item.addContextMenuItems(menuitems)
        listing.append(
            (plugin.url_for(get_video, article.find('a', {'class': 'img'})['href']), list_item, False))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


# @ plugin.route('/list_live/')
# def list_live():
#     xbmcplugin.setContent(plugin.handle, 'tvshows')
#     soup = get_page(_baseurl+'sledujte-zive')
#     listing = []
#     articles = soup.find('ul', {
#         'class': 'js-channels-navigation-carousel'}).findAll('li')
#     for article in articles:
#         if article.find('a', {'data-channel-id': re.compile(r"[0-9]+")}):
#             channel = article.find(
#                 'span', {'class': 'e-logo'}).find('img')
#             title = channel['alt']
#             if article.find('li', {'class': 'e-channel'}):
#                 show = article.find('h4').get_text()
#                 if show:
#                     plot = '{0} -{1}'.format(article.find('span', {'class': 'e-time-start'}).get_text(
#                     ), article.find('span', {'class': 'e-time-end'}).get_text())
#                     label = u'[COLOR blue]{}[/COLOR] · {}'.format(title, show)
#             else:
#                 show = None
#                 plot = None
#                 label = u'[COLOR blue]{}[/COLOR]'.format(title)
#             list_item = xbmcgui.ListItem(label)
#             list_item.setInfo(
#                 'video', {'mediatype': 'tvshow', 'tvshowtitle': title, 'title': show, 'plot': plot, 'playcount': 0})
#             list_item.setArt({'poster': channel['src']})
#             list_item.setProperty('IsPlayable', 'true')
#             listing.append(
#                 (plugin.url_for(get_live, article.find('a')['href']), list_item, False))

#     xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
#     xbmcplugin.endOfDirectory(plugin.handle)


@ plugin.route('/get_list/')
def get_list():
    xbmcplugin.setContent(plugin.handle, 'episodes')
    listing = []
    url = plugin.args['show_url'][0]
    category = plugin.args['category'][0]
    if category == 'True':
        list_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30007))
        listing.append(
            (plugin.url_for(get_category, show_url=url), list_item, True))
        url = plugin.args['show_url'][0]+'/videa/cele-dily'
    soup = get_page(url)
    articles = soup.find(
        'div', 'c-article-wrapper').find_all('article', 'c-article')
    count = 0
    for article in articles:
        # if article.find('span', {'class': 'e-label'})["class"][1] != 'voyo':
        # title = article.a['title']
        # dur = article.find('span', {'class': 'e-duration'})
        # if dur:
        #     dur = get_duration(dur.get_text())
        # list_item = xbmcgui.ListItem(title)
        # list_item.setInfo('video', {
        #     'mediatype': 'episode', 'tvshowtitle': showtitle, 'title': title, 'duration': dur})
        # list_item.setArt({'thumb': article.a.img['data-original']})
        # list_item.setProperty('IsPlayable', 'true')
        show_title = article['data-tracking-tile-show-name']
        title = article['data-tracking-tile-name']

        list_item = xbmcgui.ListItem(
            u'[COLOR blue]{0}[/COLOR] · {1}'.format(show_title, title))
        dur = article.find('time', {'class': 'duration'})
        show_url = article.find('a', {'class': 'category'})['href']
        # menuitems.append((_addon.getLocalizedString(30005), 'Container.Update(' +
        #                  plugin.url_for(get_list, category='True', show_url=show_url)+')'))
        if dur:
            dur = get_duration(dur.get_text())
        list_item.setInfo(
            'video', {'mediatype': 'episode', 'tvshowtitle': show_title, 'title': title, 'aired': article.find('time', {'class': 'date'})['datetime'], 'duration': dur})
        list_item.setArt(
            {'icon': img_res(article.find('picture').find('source')['data-srcset'])})
        list_item.setProperty('IsPlayable', 'true')
        # list_item.addContextMenuItems(menuitems)
        listing.append(
            (plugin.url_for(get_video, article.find('a', {'class': 'img'})['href']), list_item, False))
        # listing.append(
        #     (plugin.url_for(get_video, article.a['href']), list_item, False))
        count += 1
    next = soup.find('div', {'class': 'js-load-more-trigger'})
    if next and count >= 5:
        list_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30004))
        listing.append((plugin.url_for(get_list, category=False, show_url=next.find(
            'button')['data-href'], showtitle=show_title), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@ plugin.route('/get_category/')
def get_category():
    listing = []
    soup = get_page(plugin.args['show_url'][0]+'/videa')
    navs = soup.find('nav', 'c-tabs')
    if navs:
        for nav in navs.find_all('a'):
            list_item = xbmcgui.ListItem(nav.get_text())
            list_item.setInfo('video', {'mediatype': 'episode'})
            listing.append((plugin.url_for(
                get_list, category='False', show_url=nav['href']), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@ plugin.route('/get_video/<path:url>')
def get_video(url):
    PROTOCOL = 'mpd'
    DRM = 'com.widevine.alpha'
    source_type = _addon.getSetting('source_type')
    soup = get_page(url)
    embeded = get_page(soup.find(
        'div', {'class': 'js-login-player'}).find('iframe')['data-src'])

    json_data = json.loads(re.compile(
        '{\"tracks\":(.+?),\"duration\"').findall(str(embeded))[0])

    if json_data:
        stream_data = json_data[source_type][0]
        list_item = xbmcgui.ListItem()

        if not 'drm' in stream_data and source_type == 'HLS':
            list_item.setPath(stream_data['src'])
        else:
            is_helper = inputstreamhelper.Helper(PROTOCOL, drm=DRM)
            if is_helper.check_inputstream():
                stream_data = json_data['DASH'][0]
                list_item.setPath(stream_data['src'])
                list_item.setContentLookup(False)
                list_item.setMimeType('application/xml+dash')
                list_item.setProperty('inputstream', 'inputstream.adaptive')
                list_item.setProperty(
                    'inputstream.adaptive.manifest_type', PROTOCOL)
                if 'drm' in stream_data:
                    drm = stream_data['drm'][1]
                    list_item.setProperty(
                        'inputstream.adaptive.license_type', DRM)
                    list_item.setProperty('inputstream.adaptive.license_key',
                                          drm['serverURL'] + '|' + 'X-AxDRM-Message=' + drm['headers'][0]['value'] + '|R{SSM}|')
        xbmcplugin.setResolvedUrl(plugin.handle, True, list_item)
    else:
        xbmcgui.Dialog().notification(_addon.getAddonInfo('name'),
                                      _addon.getLocalizedString(30006), xbmcgui.NOTIFICATION_ERROR, 5000)

# @ plugin.route('/get_live/<path:url>')
# def get_live(url):
#     soup = get_page(url)
#     embeded = get_page(soup.find(
#         'div', {'class': 'b-image'}).find('iframe')['src']).find_all('script')[-1]

#     json_data = json.loads(re.compile(
#         '{\"tracks\":(.+?),\"duration\"').findall(str(embeded))[0])
#     if json_data:
#         stream_data = json_data['HLS'][0]
#         list_item = xbmcgui.ListItem()
#         list_item.setPath(
#             stream_data['src']+'|Referer=https://media.cms.nova.cz/')
#         xbmcplugin.setResolvedUrl(plugin.handle, True, list_item)
#     else:
#         xbmcgui.Dialog().notification(_addon.getAddonInfo('name'),
#                                       _addon.getLocalizedString(30006), xbmcgui.NOTIFICATION_ERROR, 5000)


def get_duration(dur):
    duration = 0
    l = dur.strip().split(':')
    for pos, value in enumerate(l[::-1]):
        duration += int(value) * 60 ** pos
    return duration


def img_res(url):
    print("puvodni"+url)
    if "314x175" in url:
        r = url.replace("314x175", "913x525")
    elif "276x383" in url:
        r = url.replace("276x383", "828x1149")
    else:
        r = url
    print("nova"+r)
    return r


def get_page(url):
    r = requests.get(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36'})
    return BeautifulSoup(r.content, 'html.parser')


@ plugin.route('/')
def root():
    listing = []

    # list_item = xbmcgui.ListItem(_addon.getLocalizedString(30008))
    # list_item.setArt({'icon': 'DefaultAddonPVRClient.png'})
    # listing.append((plugin.url_for(list_live), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30001))
    list_item.setArt({'icon': 'DefaultRecentlyAddedEpisodes.png'})
    listing.append((plugin.url_for(list_recent), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30003))
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    listing.append((plugin.url_for(list_shows_menu), list_item, True))

    # list_item = xbmcgui.ListItem(_addon.getLocalizedString(30002))
    # list_item.setArt({'icon': 'DefaultTVShows.png'})
    # listing.append((plugin.url_for(list_shows, 0), list_item, True))

    # list_item = xbmcgui.ListItem("Nejnovější"+_addon.getLocalizedString(30002))
    # list_item.setArt({'icon': 'DefaultTVShows.png'})
    # listing.append((plugin.url_for(list_shows, 1), list_item, True))

    # list_item = xbmcgui.ListItem(_addon.getLocalizedString(30003))
    # list_item.setArt({'icon': 'DefaultTVShows.png'})
    # listing.append((plugin.url_for(list_shows, 2), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


def run():
    plugin.run()
