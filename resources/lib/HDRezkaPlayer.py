# -*- coding: utf-8 -*-
# HDRezkaPlayer: playback monitor reporting watch progress to the site
# ("continue watching"), so it shows up in the continue list.
# Only reacts to items resolved by this addon (addon_id property);
# everything else is ignored. No dialogs here, ever (service context).

import time

import xbmc
import xbmcaddon

from helpers import log


class HDRezkaPlayer(xbmc.Player):

    def __init__(self):
        super(HDRezkaPlayer, self).__init__()
        self.addon_id = xbmcaddon.Addon().getAddonInfo('id')
        self.current_video = None
        self.last_position = 0
        self.is_paused = False

    def onAVStarted(self):
        item = self.getPlayingItem()
        if not item:
            return
        if item.getProperty('addon_id') != self.addon_id:
            return
        # the tag may not be ready the very same tick (ours only, no stall on foreign video)
        xbmc.sleep(1000)
        self.current_video = {
            'post_id': item.getProperty('post_id'),
            'translator_id': item.getProperty('translator_id'),
            'season': item.getProperty('season'),
            'episode': item.getProperty('episode'),
            'duration': self.getTotalTime(),
            'start_time': time.time(),
        }
        self.last_position = 0
        log('HDRezkaPlayer started: %s' % self.current_video)

    def onPlayBackStopped(self):
        if self.current_video:
            self._send_stats_to_server('stopped')

    def onPlayBackEnded(self):
        if self.current_video:
            self._send_stats_to_server('completed')

    def onPlayBackPaused(self):
        self.is_paused = True
        self.last_position = self.getTime()

    def onPlayBackResumed(self):
        self.is_paused = False

    def _send_stats_to_server(self, status):
        video, self.current_video = self.current_video, None
        if not video or not video.get('post_id'):
            return
        duration = int(video.get('duration') or 0)
        current_time = int(self.last_position) if status == 'stopped' else duration
        data = {
            'post_id': video['post_id'],
            'translator_id': video['translator_id'],
            'season': video['season'],
            'episode': video['episode'],
            'current_time': current_time,
            'duration': duration,
        }
        log('HDRezkaPlayer send_save data: %s' % data)
        self._send_http_post(data)

    def _send_intermediate_save(self):
        if not self.current_video or not self.current_video.get('post_id'):
            return
        if self.last_position <= 0:
            return
        data = {
            'post_id': self.current_video['post_id'],
            'translator_id': self.current_video['translator_id'],
            'season': self.current_video['season'],
            'episode': self.current_video['episode'],
            'current_time': int(self.last_position),
            'duration': int(self.current_video.get('duration') or 0),
        }
        log('HDRezkaPlayer periodic autosave: %s' % data)
        self._send_http_post(data)

    @staticmethod
    def _send_http_post(data):
        from default import HdrezkaTV, USER_AGENT
        hdrezka = HdrezkaTV()
        if not hdrezka.addon.getSetting('cookies'):
            log('HDRezkaPlayer: user not logged in, skipping cloud save')
            return
        url = '%s/ajax/send_save/?t=%d' % (hdrezka.url, int(time.time()))
        headers = {
            'Host': hdrezka.domain,
            'Origin': hdrezka.url,
            'Referer': hdrezka.url,
            'User-Agent': USER_AGENT,
            'X-Requested-With': 'XMLHttpRequest',
        }
        try:
            response = hdrezka.make_response('POST', url, data=data, headers=headers)
            log('HDRezkaPlayer send_save status: %s body: %s' % (response.status_code, response.text))
            hdrezka._save_session()
        except Exception as ex:
            log('HDRezkaPlayer send_save fault ex: %s' % ex)
