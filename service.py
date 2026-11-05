# -*- coding: utf-8 -*-
# Background service: keeps HDRezkaPlayer alive to report watch progress
# to the site ("continue watching"). No UI here.

import os
import sys

ADDON_PATH = os.path.dirname(__file__)
LIB_PATH = os.path.join(ADDON_PATH, "resources", "lib")
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)
if ADDON_PATH not in sys.path:
    sys.path.insert(0, ADDON_PATH)

import time
import xbmc

from helpers import log
from resources.lib.HDRezkaPlayer import HDRezkaPlayer


if __name__ == '__main__':
    player = HDRezkaPlayer()
    monitor = xbmc.Monitor()
    last_autosave = time.time()

    while not monitor.abortRequested():
        if player.current_video and not player.is_paused and player.isPlaying():
            try:
                player.last_position = player.getTime()
                total_time = player.getTotalTime()
                if total_time > 0 and (not player.current_video.get('duration') or player.current_video['duration'] <= 0):
                    player.current_video['duration'] = total_time

                # Periodic cloud sync every 60 seconds
                if time.time() - last_autosave >= 60:
                    player._send_intermediate_save()
                    last_autosave = time.time()
            except Exception as ex:
                log('service fault getTime ex: %s' % ex)
        if monitor.waitForAbort(10):
            break
