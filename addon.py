# -*- coding: utf-8 -*-
import urllib2,urllib,re,os,string,time,base64,datetime

from parseutils import *
import xbmcplugin,xbmcgui,xbmcaddon

__baseurl__ = 'http://novaplus.nova.cz'
__dmdbase__ = 'http://iamm.uvadi.cz/xbmc/voyo/'
_UserAgent_ = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'
addon = xbmcaddon.Addon('plugin.video.novaplus.cz')
profile = xbmc.translatePath(addon.getAddonInfo('profile'))
__settings__ = xbmcaddon.Addon(id='plugin.video.novaplus.cz')
home = __settings__.getAddonInfo('path')

addon_handle = int(sys.argv[1])

def log(msg, level=xbmc.LOGDEBUG):
    if type(msg).__name__ == 'unicode':
        msg = msg.encode('utf-8')
    xbmc.log("[%s] %s" % (addon, msg.__str__()), level)

def logDbg(msg):
    log(msg,level=xbmc.LOGDEBUG)

def OBSAH():
    addDir('Poslední díly','https://novaplus.nova.cz',2,)
    addDir('TOP pořady','https://novaplus.nova.cz',3)
    addDir('Všechny pořady','https://novaplus.nova.cz/porady/',4)
    addDir('Televizní noviny','https://novaplus.nova.cz/porad/televizni-noviny',5)

def HOME_POSLEDNI(url):
    doc = read_page(url)
   
    for section in doc.findAll('section', 'b-main-section b-section-articles my-5'):
        if section.h3.getText(" ").encode('utf-8') == 'POSLEDNÍ DÍLY':
            for article in section.div.findAll('article'):
                url = article.a['href'].encode('utf-8')
                title = article.a['title'].encode('utf-8')
               
                thumb = article.a.div.img['data-original'].encode('utf-8')
                dur=article.find('span', {'class': 'e-duration'}).text
                if dur and ':' in dur:
                    l = dur.strip().split(':')
                    duration = 0
                    for pos, value in enumerate(l[::-1]):
                        duration += int(value) * 60 ** pos
                addResolvedLink(title,url,thumb,duration)

def HOME_TOPPORADY(url):
    doc = read_page(url)

    for section in doc.findAll('section', 'b-main-section my-sm-5'):
        if section.div.h3.getText(" ").encode('utf-8') == 'TOP POŘADY':
            for article in section.findAll('article'):
                url = article.a['href'].encode('utf-8')
                title = article.a['title'].encode('utf-8')
                thumb = article.a.div.img['data-original'].encode('utf-8')
                addDir(title,url,5,thumb)

def SHOWS(url):
    logDbg('CATEGORIES *********************************' + str(url))
    doc = read_page(url)
    xbmcplugin.addSortMethod( handle = addon_handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL )
    shows = doc.find("div", {"class": "b-show-listing"})
    for article in shows.findAll('article'):
        for link in article.findAll('a', href=re.compile(r'novaplus\.nova\.cz') ):
            url, title, thumb = None, None, None
            url = link['href'].encode('utf-8')
            title = link['title'].encode('utf-8')
            thumb = link.div.img['data-original'].encode('utf-8')
            addDir(title,url,5,thumb)

def EPISODES(url):
    logDbg('EPISODES *********************************' + str(url))

    doc = read_page(url)
    
    articles = doc.find('div', 'col-md-12 col-lg-8 order-3')
    title=doc.find('title').text
    url=doc.find('link', rel='canonical')
    thumb=doc.find('meta', property='og:image')
    logDbg("**********************************************"+url['href'])
    
    addResolvedLink(title.split(" | ")[0].encode('utf-8'),url['href'].encode('utf-8'),thumb['content'].encode('utf-8'), 0)

    # dalsi dily poradu
    for article in articles.findAll('article', 'b-article-news'):
        url = article.a['href'].encode('utf-8')
        title = article.a['title'].encode('utf-8')
        thumb = article.a.img['data-original'].encode('utf-8')
        '''dur=article.find('span', {'class': 'e-duration'}).text
        if dur and ':' in dur:
            l = dur.strip().split(':')
            duration = 0
            for pos, value in enumerate(l[::-1]):
                duration += int(value) * 60 ** pos'''
        addResolvedLink(title,url,thumb,'')

def VIDEOLINK(url):
    logDbg('VIDEOLINK *********************************' + str(url))

    doc = read_page(url)

    # zjisteni nazvu a popisu aktualniho dilu
    article = doc.find('article', 'b-article b-article-main')
    # nazev
    name = article.find('h3').getText(" ").encode('utf-8')
    # popis nemusi byt vzdy uveden
    try:
      desc = article.find('div', 'e-description').getText(" ").encode('utf-8')
    except:
      desc = ''

    # nalezeni iframe
    main = doc.find('main')
    url = main.find('iframe')['src']
    logDbg(' - iframe src ' + str(url))

    # nacteni a zpracovani iframe
    req = urllib2.Request(url)
    req.add_header('User-Agent', _UserAgent_)
    response = urllib2.urlopen(req)
    httpdata = response.read()
    response.close()

    httpdata   = httpdata.replace("\r","").replace("\n","").replace("\t","")

    thumb = re.compile('<meta property="og:image" content="(.+?)">').findall(httpdata)
    thumb = thumb[0] if len(thumb) > 0 else ''

    bitrates = re.compile('src = {(.+?)\[(.+?)\]').findall(httpdata);
    if len(bitrates) > 0:
        urls = re.compile('[\'\"](.+?)[\'\"]').findall(bitrates[0][1])
        liz = xbmcgui.ListItem()
        liz = xbmcgui.ListItem(path=urls[-1])  
        liz.setInfo( type="Video", infoLabels={ "Title": name, 'Plot': desc})
        liz.setProperty('isPlayable', 'true')
        xbmcplugin.setResolvedUrl(handle=addon_handle, succeeded=True, listitem=liz)
    else:
        xbmcgui.Dialog().ok('Chyba', 'Video nelze přehrát', '', '')

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

def addResolvedLink(name, url, iconimage, dur):
    xbmcplugin.setContent(addon_handle, 'episodes')
    return addItem(name, url, 6, iconimage, dur, False)
    
def addItem(name, url, mode, iconimage, dur, isfolder):  
    u=sys.argv[0]+"?url="+urllib.quote_plus(url)+"&mode="+str(mode)+"&name="+urllib.quote_plus(name)
    ok=True
    liz=xbmcgui.ListItem(name, iconImage="DefaultFolder.png", thumbnailImage=iconimage)
    liz.setInfo(type="Video", infoLabels={"Title": name})
    liz.setProperty("Fanart_Image", iconimage)
    if u'dur':
        liz.setInfo('video', {'duration': dur})
    if not isfolder:
        liz.setProperty("isPlayable", "true")
    ok=xbmcplugin.addDirectoryItem( handle = addon_handle,url=u,listitem=liz,isFolder=isfolder )
    return ok

def addDir(name,url,mode,iconimage=''):
    return addItem(name, url, mode, iconimage, 0, True)

params=get_params()
url=None
name=None
thumb=None
mode=None

try:
    url=urllib.unquote_plus(params["url"])
except:
    pass
try:
    name=urllib.unquote_plus(params["name"])
except:
    pass
try:
    mode=int(params["mode"])
except:
    pass

logDbg("Mode: "+str(mode))
logDbg("URL: "+str(url))
logDbg("Name: "+str(name))

if mode==None or url==None or len(url)<1:
    OBSAH()
elif mode==2:
    HOME_POSLEDNI(url)
elif mode==3:
    xbmcplugin.setContent(addon_handle, 'tvshows')
    HOME_TOPPORADY(url)
elif mode==4:
    xbmcplugin.setContent(addon_handle, 'tvshows')
    SHOWS(url)
elif mode==5:
    EPISODES(url)
elif mode==6:
    VIDEOLINK(url)

xbmcplugin.endOfDirectory(addon_handle)