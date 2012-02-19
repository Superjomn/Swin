# -*- coding: utf-8 -*-

######################## BEGIN LICENSE BLOCK ########################
# The Initial Developer of the Original Code is
# Chunwei from China Agricual University
# Portions created by the Initial Developer are Copyright (C) 2012
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
# Chunwei  Mail: superjom@gmail.com
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
# 02110-1301 USA
######################### END LICENSE BLOCK #########################
'''
Created on Feb 12, 2012

@author: chunwei
'''
#-------------------------------------------------------------
import os
import threading  
import time  
import urllib2  
import StringIO  
import gzip  
import string  
import chardet
import httplib
import datetime as datetime

import urlparse
#-------------------------------------------------------------
from judger import Judger

from List import Urlist
from List import UrlQueue
from List import Queue

from sourceparser import HtmlParser
from sourceparser import PicParser

from iofile import DBSource
from iofile import Collector
#-------------------------------------------------------------

'''
新特性：
    从urlib2 更替为 httplib 一次分配一个站点的爬取任务 重复利用DNS缓存
'''
class Reptile:
    '''
    单个线程
    '''
    def __init__(self, name, url_queue, url_list, url_in_queue, Flock, home_urls ,tem_siteID = [0]):
        '''
        name
        url_queue       从主服务器中分配到的url
        url_list        本地区分是否重复
        url_in_queue    解析得到的新url    将为每一个站点分配一个 UrlQueue
        Flock
        home_urls       测试是否符合爬取集合
        tem_conn        初始的DNS 缓存
        is_new_task     通过引用传递 由communitor修改  以判断是否需要修改
        tem_home_url    
        old_home_url    引用传递
        '''
        #threading.Thread.__init__(self, name = name )  
        #本地测试url队列 如果在本地重复 则直接舍弃
        #如果不重复 加入临时队列 将来传输到中央服务器进行测试
        #为每个站点分配了一个list对象 分开进行url的分辨
        self.__url_list = url_list
        self.__url_queue = url_queue
        #默认为每一个站点分配一个inqueue
        #本地临时记录队列 在url_list中测试不重复后 加入in_queue
        #在积累到一定量后 传输给中央服务器管理
        self.__url_in_queue = url_in_queue
        #----------------------------------------------------------------
        self.__Flock = Flock
        self.__home_urls = home_urls
        #强制刷新 DNS
        self.__tem_siteID = -1
        self.__siteID = tem_siteID
        #----------------------------------------------------------------
        self.__Flock = Flock
        self.__htmlparser = HtmlParser()
        self.__picparser = PicParser()
        self.__judger = Judger(self.__home_urls)
        #init temporary home_url and siteID
        #both to determine weather to refresh DNS cache
        #引用传递 方便进行对照
        self.__dbsource = DBSource()
        self.__collector = Collector()

    def init(self, siteID):
        self.siteID = siteID
        self.__dbsource.init(siteID)
    
    def conn(self):
        '''
        包含刷新DNS功能
        siteID引用传入  检测DNS改变
        '''
        if self.__tem_siteID != self.__siteID[0]:
            '''
            更新DNS
            '''
            self.__tem_siteID = self.__siteID[0]
            netloc = (urlparse.urlsplit(self.__home_urls[self.__tem_siteID])).netloc
            print 'netloc',netloc
            self.__conn = httplib.HTTPConnection(netloc, 80, timeout = 10)
        return self.__conn

    def transcode(self, source):
        res = chardet.detect(source)
        confidence = res['confidence']
        encoding = res['encoding']
        print 'transcode', res
        if confidence < 0.6:
            return False
        else:
            return unicode(source, encoding)
        
    def run(self):
        '''
        运行主程序
        '''
        while(True):
            urlinfo = self.getAUrl()
            if not len(urlinfo):
                print "No Task\nqueue is empty!"
                #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!i多线程时需要更多优化
                return
            source = self.getPage(urlinfo[1])
            #print source
            if not self.__htmlparser.init(source):
                continue
            self.saveHtml(urlinfo[1], urlinfo[0])
            imgsrcs = self.getImgUrls()
            if imgsrcs:
                '''
                if there are pictures, download them
                '''
                for src in imgsrcs:
                    imgsource = self.getImg(src)
                    self.picparser.init(imgsource)
                    size = self.picparser.getSize()
                    info = {
                        'url':src,
                        'width':size[0],
                        'height':size[1]
                    }
                    self.saveImg(info, imgsource)
            newurls = self.htmlparser.getALinkText_List()
            self.AddNewInQueue(self.__cur_pageurl, newurls)
    
    def requestSource(self, path):
        '''
        page_url    子页面 如 ./index.html
        url: 直接传入绝对url 包括home_url
        内部进行解析
        '''
        print '<requestSource>'
        print 'request url>',path
        conn = self.conn()
        conn.request("GET", path)
        #print self.__conn
        r1 = conn.getresponse()
        #print r1
        print r1.status
        data = r1.read()
        '''
        if r1.status != 'OK':
            print 'status is ',r1.status
            print 'status not OK'
            print r1.reason
            return False
        data = r1.read()
        if not len(data):
            print 'length of data is 0'
            return False
        '''
        return data
    
    def getPage(self, path):
        '''
        path_url     './home/index.php'
        '''
        print 'page_url',path
        data = self.requestSource(path)
        if len(data):
            data = self.transcode(data)
            if not data:
                return False
            self.__collector.init(data)
            self.__htmlparser.init(data)
        return data
        
    
    def getImg(self, path):
        '''
        img_url    './img/1.jpg'
        '''
        return self.requestSource(path)
    
    def getAUrl(self):
        if self.__url_queue.size() > 0:
            return self.__url_queue.pop()
        else:
            return False
    
    def getUrls(self):
        '''
        取得urls
        并且进行判断 
        '''
        return self.__htmlparser.getALink_Dic()
    
    def getImgUrls(self):
        '''
        parse html source and return src_list
        '''
        return self.__htmlparser.getPicSrcs_List()
        
    def AddNewInQueue(self, page_url, url_list):
        '''
        url直接为原始的url   不需要另外进行处理
        将new_url添加到对应的queue中
        '''
        for url in url_list:
            #处理为绝对url
            url = self.__judger.transToStdUrl(page_url, url)
            siteID = self.__judger.judgeUrl(page_url, url)
            path = urlparse.urlsplit(url).path
            #判断是否为本平台url
            if siteID != -1:
                if not self.__url_list.find(siteID, path):
                    '''
                    not duplicate in url_list
                    '''
                    #将url减少
                    self.__url_in_queue(siteID, path)

    def saveHtml(self, url, title):
        '''
        存储 source 和 parsedsource to database
        '''
        today = datetime.date.today()
        info = {
            'title' :   title,
            'url':      url,
            'date':     datetime.date.isoformat(today)
        }
        self.__dbsource.saveHtml(info, self.__collector.html, self.__collector.transXml_Str(url))

    def saveImg(self, info, source):
        imgsource = self.picparser.compressedPic(source)
        self.__dbsource.saveImg(info, imgsource)

if __name__ == '__main__':
    home_urls = [
        "http://www.cau.edu.cn",
        "http://www.baidu.com"
    ]
    home_num = len(home_urls)
    l = Urlist(home_num)
    q = UrlQueue(home_urls)
    queue = Queue()
    queue.init(0, 'http://www.cau.edu.cn')
    queue.append("cau","http://www.cau.edu.cn")

    name = "reptile"
    Flock = threading.RLock()  
    print 'home_url >',home_urls[0]

    home_url = home_urls[0]
    print home_url

    tem_siteID = [0]

    r = Reptile(name, queue, l, q, Flock, home_urls, tem_siteID)
    r.init(0)
    print r.getPage('/')
    print r.getUrls()
    print r.getImgUrls()

