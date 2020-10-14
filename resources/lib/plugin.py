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

_baseurl = 'https://novaplus.nova.cz/'

@plugin.route('/list_shows/<type>')
def list_shows(type):
    xbmcplugin.setContent(plugin.handle, 'tvshows')
    soup = get_page(_baseurl+'porady')
    listing = []
    articles = soup.find_all('div', {'class': 'b-show-listing'})[int(type)].find('div', {'class': 'b-tiles-wrapper'}).find_all('a')
    for article in articles:
        title = article['title'].encode('utf-8')
        list_item = xbmcgui.ListItem(label=title)
        list_item.setInfo('video', {'mediatype': 'tvshow', 'title': title})
        list_item.setArt({'poster': article.div.img['data-original']})
        listing.append((plugin.url_for(get_list, category = False, show_url = article['href'], showtitle = title), list_item, True))
    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/list_recent/')
def list_recent():
    xbmcplugin.setContent(plugin.handle, 'episodes')
    soup = get_page(_baseurl)
    listing = []
    articles = soup.find('section', {'class':'b-main-section b-section-articles my-5'}).find_all('article', {'class':'b-article b-article-no-labels'})
    for article in articles:
        menuitems = []
        title = article.find('span', {'class':'e-text'}).get_text()
        dur = article.find('span', {'class':'e-duration'})
        show_url = re.compile('(.+)\/.+\/').findall(article.find('a')['href'])[0]
        menuitems.append(( _addon.getLocalizedString(30005), 'XBMC.Container.Update('+plugin.url_for(get_list, category = False, show_url = show_url)+')' ))
        if dur:
            dur = get_duration(article.find('span', {'class':'e-duration'}).get_text())
        list_item = xbmcgui.ListItem(label = title)
        list_item.setInfo('video', {'mediatype': 'episode', 'title': title, 'duration': dur})
        list_item.setArt({'icon': article.find('img', {'class':'e-image'})['data-original']})
        list_item.setProperty('IsPlayable', 'true')
        list_item.addContextMenuItems(menuitems)
        listing.append((plugin.url_for(get_video, article.find('a')['href']), list_item, False))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/get_list/')
def get_list():
    xbmcplugin.setContent(plugin.handle, 'episodes')
    listing = []  
    url = plugin.args['show_url'][0]
    category = plugin.args['category'][0]
    if category == 'False':
        list_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30007))
        listing.append((plugin.url_for(get_category, show_url = url), list_item, True))
        url = plugin.args['show_url'][0]+'/cele-dily'
    soup = get_page(url)
    if 'showtitle' in plugin.args:
        showtitle = plugin.args['showtitle'][0].encode('utf-8')
    else:
        showtitle = soup.find('h1', 'title').get_text().encode('utf-8')
    articles = soup.find_all('article', 'b-article-news m-layout-playlist')
    count = 0
    for article in articles:
        if article.find('span', {'class': 'e-label'})["class"][1] != 'voyo':
            get_page(url)
            title = article.a['title']
            dur = article.find('span', {'class':'e-duration'})
            if dur:
                dur = get_duration(dur.get_text())
            list_item = xbmcgui.ListItem(title)
            list_item.setInfo('video', {'mediatype': 'episode', 'tvshowtitle': showtitle, 'title': title, 'duration': dur})
            list_item.setArt({'thumb': article.a.img['data-original']})
            list_item.setProperty('IsPlayable', 'true')
            listing.append((plugin.url_for(get_video, article.a['href']), list_item, False))
            count +=1
    next = soup.find('div', {'class': 'e-load-more'})
    if next and count == 5:
        list_item = xbmcgui.ListItem(label=_addon.getLocalizedString(30004))
        listing.append((plugin.url_for(get_list, category = category, show_url = next.find('button')['data-href'], showtitle = showtitle), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/get_catogory/')
def get_category():
    listing = []
    soup = get_page(plugin.args['show_url'][0])
    navs = soup.find('nav', 'navigation js-show-detail-nav')
    if navs:
        for nav in navs.find_all('a'):
            list_item = xbmcgui.ListItem(nav['title'])
            list_item.setInfo('video', {'mediatype': 'episode'})
            listing.append((plugin.url_for(get_list, category = True, show_url = nav['href']), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/get_video/<path:url>')
def get_video(url):
    PROTOCOL = 'mpd'
    DRM = 'com.widevine.alpha'
    source_type = _addon.getSetting('source_type')
    soup = get_page(url)
    desc = soup.find('meta', {'name':'description'})['content'].encode('utf-8').replace('&nbsp;',' ')
    showtitle = soup.find('h1', {'class':'title'}).find('a').get_text().encode('utf-8')
    title = soup.find('h2', {'class':'subtitle'}).get_text().encode('utf-8')
    embeded = get_page(soup.find('div', {'class':'b-image video'}).find('iframe')['src']).find_all('script')[-1].get_text()
    json_data = json.loads(re.compile('{\"tracks\":(.+?),\"duration\"').findall(embeded)[0])
    if json_data:
        stream_data = json_data[source_type][0]
        list_item = xbmcgui.ListItem()
        list_item.setInfo('video', {'mediatype': 'episode', 'tvshowtitle': showtitle, 'title': title, 'plot' : desc})
        if not 'drm' in stream_data and source_type == 'HLS':   
            list_item.setPath(stream_data['src'])
        else:
            is_helper = inputstreamhelper.Helper(PROTOCOL, drm=DRM)
            if is_helper.check_inputstream():
                stream_data = json_data['DASH'][0]
                list_item.setPath(stream_data['src'])
                list_item.setContentLookup(False)
                list_item.setMimeType(stream_data['type'])
                list_item.setProperty('inputstream.adaptive.manifest_type', PROTOCOL)
                list_item.setProperty('inputstreamaddon', is_helper.inputstream_addon)
                if 'drm' in stream_data:
                    drm = stream_data['drm'][1]
                    list_item.setProperty('inputstream.adaptive.license_type', DRM)
                    list_item.setProperty('inputstream.adaptive.license_key', drm['serverURL'] + '|' + 'X-AxDRM-Message=' + drm['headers'][0]['value'] + '|R{SSM}|')
        xbmcplugin.setResolvedUrl(plugin.handle, True, list_item)
    else:
        xbmcgui.Dialog().notification(_addon.getAddonInfo('name'),_addon.getLocalizedString(30006), xbmcgui.NOTIFICATION_ERROR, 5000)

def get_duration(dur):
    duration = 0
    l = dur.strip().split(':')
    for pos, value in enumerate(l[::-1]):
        duration += int(value) * 60 ** pos
    return duration

def get_page(url):
    r = requests.get(url, headers={'User-Agent': 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0'})
    return BeautifulSoup(r.content, 'html.parser')

@plugin.route('/')
def root():
    listing = []
    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30001))
    list_item.setArt({'icon': 'DefaultRecentlyAddedEpisodes.png'})
    listing.append((plugin.url_for(list_recent), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30002))
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    listing.append((plugin.url_for(list_shows, 0), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30003))
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    listing.append((plugin.url_for(list_shows, 1), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

def run():
    plugin.run()
