# -*- coding: utf-8 -*-
"""
Kodi cross-version compatibility utilities.
Supports Kodi 19 (Matrix), 20 (Nexus), 21 (Omega), and 22 (Piers).
"""

import os
import sys

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    import xbmcvfs
    IS_KODI = True
except ImportError:
    IS_KODI = False


def log(msg, level=None):
    """Safe logging function."""
    if not IS_KODI:
        print("[HDRezka] {}".format(msg))
        return
    if level is None:
        level = xbmc.LOGINFO
    xbmc.log("[plugin.video.hdrezka.tv] {}".format(msg), level)


def get_profile_path(addon_id="plugin.video.hdrezka.tv"):
    """Returns absolute path to the addon's profile (data) directory."""
    if not IS_KODI:
        path = os.path.expanduser("~/.kodi_data/hdrezka")
        os.makedirs(path, exist_ok=True)
        return path
    
    addon = xbmcaddon.Addon(addon_id)
    profile_url = addon.getAddonInfo("profile")
    path = xbmcvfs.translatePath(profile_url)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path


def set_video_info(item, info):
    """
    Sets video metadata on a ListItem compatible with both old and modern Kodi versions (Kodi 20, 21, 22).
    """
    if not IS_KODI or not item or not info:
        return

    # Modern Kodi 20+ / 21 / 22 VideoInfoTag API
    if hasattr(item, "getVideoInfoTag"):
        try:
            tag = item.getVideoInfoTag()
            if "title" in info and info["title"]:
                tag.setTitle(str(info["title"]))
            if "originaltitle" in info and info["originaltitle"]:
                tag.setOriginalTitle(str(info["originaltitle"]))
            if "plot" in info and info["plot"]:
                tag.setPlot(str(info["plot"]))
            if "year" in info and info["year"]:
                try:
                    tag.setYear(int(info["year"]))
                except (ValueError, TypeError):
                    pass
            if "rating" in info and info["rating"]:
                try:
                    tag.setRating(float(info["rating"]))
                except (ValueError, TypeError):
                    pass
            if "genre" in info and info["genre"]:
                genres = [g.strip() for g in info["genre"].split(",") if g.strip()]
                tag.setGenres(genres)
            if "country" in info and info["country"]:
                countries = [c.strip() for c in info["country"].split(",") if c.strip()]
                tag.setCountries(countries)
            if "mediatype" in info and info["mediatype"]:
                tag.setMediaType(str(info["mediatype"]))
            if "season" in info and info["season"] is not None:
                try:
                    tag.setSeason(int(info["season"]))
                except (ValueError, TypeError):
                    pass
            if "episode" in info and info["episode"] is not None:
                try:
                    tag.setEpisode(int(info["episode"]))
                except (ValueError, TypeError):
                    pass
            return
        except Exception as e:
            log("getVideoInfoTag fallback to setInfo: {}".format(e), xbmc.LOGDEBUG)

    # Legacy fallback for Kodi 18 / 19
    try:
        item.setInfo(type="video", infoLabels=info)
    except Exception as e:
        log("setInfo failed: {}".format(e), xbmc.LOGWARNING)


def set_art(item, art_dict):
    """Sets artwork on a ListItem."""
    if not IS_KODI or not item or not art_dict:
        return
    cleaned = {k: v for k, v in art_dict.items() if v}
    if hasattr(item, "setArt"):
        item.setArt(cleaned)
    else:
        if "icon" in cleaned:
            item.setIconImage(cleaned["icon"])
        if "thumb" in cleaned:
            item.setThumbnailImage(cleaned["thumb"])
