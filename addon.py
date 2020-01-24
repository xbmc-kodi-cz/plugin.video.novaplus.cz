# -*- coding: utf-8 -*-
import re
import datetime
from bs4 import BeautifulSoup
import requests
import urllib
import xbmcplugin
import xbmcgui
import xbmcaddon
import urlparse

_baseurl_ = 'https://novaplus.nova.cz/'
_useragent_ = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36'
_addon = xbmcaddon.Addon('plugin.video.novaplus.cz')
_lang = _addon.getLocalizedString

addon_handle = int(sys.argv[1])

def log(msg, level=xbmc.LOGDEBUG):
    if type(msg).__name__ == 'unicode':
        msg = msg.encode('utf-8')
    xbmc.log('[%s] %s' % (_addon, msg.__str__()), level)

def logDbg(msg):
    log(msg,level=xbmc.LOGDEBUG)

def _fetch(url):
    logDbg('_fetchUrl ' + url)
    resp = requests.get(url, headers={'User-Agent': _useragent_})
    return BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')

def _thumb(url):
    th_size_w = ''
    th_size_h = ''
    
    th_size = re.search('r(.+?)x(.+?)n', url)   
    
    if th_size.group(1) == th_size.group(2):
        th_size_w = 512
        th_size_h = 512
    else:
        th_size_w = 640
        th_size_h = 362       
    return re.sub('r(.+?)x(.+?)n', 'r'+str(th_size_w)+'x'+str(th_size_h)+'n', url)
    
def _dur(dur):
    if dur and ':' in dur:
        l = dur.strip().split(':')
        duration = 0
        for pos, value in enumerate(l[::-1]):
            duration += int(value) * 60 ** pos
    return duration
    
def CONTENT():
    addDir(_lang(30001), _baseurl_+'porady', 4)
    doc = _fetch(_baseurl_)
    for section in doc.find_all('section', 'b-main-section'):
        if section.find('h3'):
            title=section.find('h3').text
            if section['class'][1] == 'b-section-articles':
                addDir(title, _baseurl_, 7)
            else:
                addDir(title, _baseurl_, 8)

def ITEMS(title, dir=False):
    doc = _fetch(_baseurl_)
    if dir == False:
        sections = doc.find_all('section', 'b-main-section b-section-articles my-5')
    else:
        sections = doc.find_all('section', 'b-main-section my-sm-5')
        
    for section in sections:
        if section.find('h3').text == title.decode('utf-8'):
            for article in section.find_all('article'):
                dur = article.find('span', {'class': 'e-duration'})
                if dur != None:
                    dur = _dur(dur.text)
                if dir == False:
                    addResolvedLink(article.a['title'], article.a['href'], _thumb(article.a.div.img['data-original']), dur)
                else:
                    xbmcplugin.setContent(addon_handle, 'tvshows')
                    addDir(article.a['title'], article.a['href'], 5, _thumb(article.a.div.img['data-original']))

def SHOWS(url):
    doc = _fetch(url)
    xbmcplugin.addSortMethod( handle = addon_handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL )
    shows = doc.find_all('div', {'class': 'b-tiles-wrapper'})
    for article in shows[1].find_all('article'):
        for link in article.find_all('a', href=re.compile(r'novaplus\.nova\.cz')):
            addDir(link['title'], link['href'], 5, link.div.img['data-original'])

def EPISODES(url, page):
    doc = _fetch(url)
    try:
        nav = doc.find('nav', {'class': 'navigation js-show-detail-nav'}).find_all('a', href=re.compile(".*cele-dily"))[0]
        doc = _fetch(nav["href"])
    except:
        nav=''

    try:
        next = doc.find('div', {'class': 'e-load-more'}).find('button')['data-href']
    except:
        next=''
        
    count = 0  
    for article in doc.find_all('article', 'b-article-news m-layout-playlist'):
        if article.find('span', {'class': 'e-label'})["class"][1] != 'voyo':
            addResolvedLink(article.find('h3').text, article.a['href'], article.a.img['data-original'], _dur(article.find('span', {'class': 'e-duration'}).text))
            count = count + 1
    if(next and count == 5):
        EPISODES(next, True)

def VIDEOLINK(url):
    doc = _fetch(url)
    iframe =_fetch(doc.find('main').find('iframe')['src']).find_all('script')[-1].text.replace('\r','').replace('\n','').replace('\t','')
    
    try:
        stream_url = re.compile('\"hls\": \"(.+?)\"').findall(iframe)[0]
        hls=True
    except:
        stream_url = re.compile('[\'\"](.+?)[\'\"]').findall(re.compile('src = {(.+?)\[(.+?)\]').findall(iframe)[0][1])[-1]
        hls=False
    if stream_url:
        play_item = xbmcgui.ListItem(path=stream_url)
        if hls==True:
            play_item.setProperty('inputstreamaddon', 'inputstream.adaptive')
            play_item.setProperty('inputstream.adaptive.manifest_type', 'hls')
        play_item.setInfo( type='video', infoLabels={ 'title': doc.find('meta', property='og:title')[u'content'], 'plot': doc.find('meta', property='og:description')[u'content']})
        xbmcplugin.setResolvedUrl(handle=addon_handle, succeeded=True, listitem=play_item)

def addResolvedLink(title, url, iconimage, duration):
    xbmcplugin.setContent(addon_handle, 'episodes')
    return addItem(title, url, 6, iconimage, duration, False)
    
def addItem(title, url, mode, iconimage, duration, isfolder):  
    u=sys.argv[0]+'?url='+urllib.quote_plus(url.encode('utf-8'))+'&mode='+str(mode)+'&title='+urllib.quote_plus(title.encode('utf-8'))
    ok=True
    liz=xbmcgui.ListItem(title, thumbnailImage=iconimage)
    liz.setInfo('video', infoLabels={'mediatype': 'episode', 'title': title, 'duration': duration})
    liz.setProperty('fanart_image', iconimage)
    if not isfolder:
        liz.setProperty('isPlayable', 'true')
    ok=xbmcplugin.addDirectoryItem( handle = addon_handle,url=u,listitem=liz,isFolder=isfolder )
    return ok

def addDir(title, url, mode, iconimage=None, isfolder=True):
    return addItem(title, url, mode, iconimage, None, True)

def get_params():
    param=[]
    paramstring=sys.argv[2]
    if len(paramstring)>=2:
        params=sys.argv[2]
        cleanedparams=params.replace('?','')
        if (params[len(params)-1]=='/'):
            params=params[0:len(params)-2]
        pairsofparams=cleanedparams.split('&')
        param={}
        for i in range(len(pairsofparams)):
            splitparams={}
            splitparams=pairsofparams[i].split('=')
            if (len(splitparams))==2:
                param[splitparams[0]]=splitparams[1]
    return param

params=get_params()
url=None
title=None
thumb=None
mode=None

try:
    url=urllib.unquote_plus(params['url'])
except:
    pass
try:
    title=urllib.unquote_plus(params['title'])
except:
    pass
try:
    mode=int(params['mode'])
except:
    pass

logDbg('Mode: '+str(mode))
logDbg('URL: '+str(url))
logDbg('Title: '+str(title))

if mode==None or url==None or len(url)<1:
    CONTENT()
elif mode==4:
    xbmcplugin.setContent(addon_handle, 'tvshows')
    SHOWS(url)
elif mode==5:
    EPISODES(url, False)
elif mode==6:
    VIDEOLINK(url)
elif mode==7:
    ITEMS(title)
elif mode==8:
    ITEMS(title, True)
elif mode==9:
    EPISODES(url, True)
xbmcplugin.endOfDirectory(addon_handle)
