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
        item = None
        for _ in range(5):
            item = self.getPlayingItem()
            if item and item.getProperty('addon_id') == self.addon_id and item.getProperty('post_id'):
                break
            xbmc.sleep(200)

        if not item or item.getProperty('addon_id') != self.addon_id or not item.getProperty('post_id'):
            return

        duration = 0
        try:
            duration = self.getTotalTime()
        except Exception:
            pass

        self.current_video = {
            'post_id': item.getProperty('post_id'),
            'translator_id': item.getProperty('translator_id') or '0',
            'season': item.getProperty('season') or '0',
            'episode': item.getProperty('episode') or '0',
            'duration': duration,
            'start_time': time.time(),
        }
        self.last_position = 0
        log('HDRezkaPlayer started: %s' % self.current_video)

    def onPlayBackStopped(self):
        if self.current_video:
            try:
                pos = self.getTime()
                if pos > 0:
                    self.last_position = pos
            except Exception:
                pass
            self._send_stats_to_server('stopped')

    def onPlayBackEnded(self):
        if self.current_video:
            self._send_stats_to_server('completed')

    def onPlayBackPaused(self):
        self.is_paused = True
        try:
            pos = self.getTime()
            if pos > 0:
                self.last_position = pos
        except Exception:
            pass
        self._send_intermediate_save()

    def onPlayBackResumed(self):
        self.is_paused = False

    def _send_stats_to_server(self, status):
        video, self.current_video = self.current_video, None
        if not video or not video.get('post_id'):
            return
        duration = int(float(video.get('duration') or 0))
        current_time = int(float(self.last_position or 0)) if status == 'stopped' else duration
        data = {
            'post_id': video['post_id'],
            'translator_id': video.get('translator_id') or '0',
            'season': video.get('season') or '0',
            'episode': video.get('episode') or '0',
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
            'translator_id': self.current_video.get('translator_id') or '0',
            'season': self.current_video.get('season') or '0',
            'episode': self.current_video.get('episode') or '0',
            'current_time': int(float(self.last_position or 0)),
            'duration': int(float(self.current_video.get('duration') or 0)),
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
