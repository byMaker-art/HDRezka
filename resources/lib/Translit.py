#!/usr/bin/python
# Writer (c) 2012-2017, MrStealth, dandy
# Rev. 2.1.0
# License: GPLv3

import os, sys, json
import xbmc, xbmcaddon, xbmcvfs
import importlib

#importlib.reload(sys)
#sys.setdefaultencoding("UTF8")

class Translit():
    def __init__(self, encoding='utf-8'):
        self.version = "2.1.0"
        self.plugin = "Translit" + self.version
        self.id = 'script.module.translit'
        try:
            self.addon = xbmcaddon.Addon(self.id)
            self.path = xbmcvfs.translatePath(self.addon.getAddonInfo('path'))
            self.resource = xbmcvfs.translatePath(os.path.join(self.path, 'lib'))
        except Exception:
            self.addon = None
            self.path = os.path.dirname(__file__)
            self.resource = self.path

        self.encoding = encoding
        self.transtable = self.getTranstable()

        if self.path not in sys.path:
            sys.path.append(self.path)

    def getTranstable(self):
        try:
            local_path = os.path.join(os.path.dirname(__file__), "transtable.json")
            if os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            file_path = os.path.join(self.resource, "transtable.json")
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return ()

    def rus(self, in_string):
        russian = str(in_string)
        for symb_out, symb_in in self.transtable:
          russian = russian.replace(symb_in, symb_out)
        return russian

    def eng(self, in_string):
        translit = str(in_string)
        for symb_out, symb_in in self.transtable:
          translit = translit.replace(symb_out, symb_in)
        return translit
