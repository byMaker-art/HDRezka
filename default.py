# -*- coding: utf-8 -*-
"""
HDRezka Add-on for Kodi
Compatible with Kodi 19, 20, 21 (Omega), and 22 (Piers).
Includes Anubis Proof-of-Work solver, mirror management, and personal account bookmarks.
"""

import os
import re
import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from lib.client import DEFAULT_USER_AGENT, RezkaClient
from lib.compat import IS_KODI, get_profile_path, log, set_art, set_video_info
from lib.history import add_to_history, clear_history, get_history
from lib.parser import (
    QUALITY_WEIGHTS,
    decode_trash_string,
    parse_catalog_items,
    parse_dom,
    parse_episodes_from_page,
    parse_stream_links,
    parse_subtitles,
    parse_translators,
    strip_tags,
)

PLUGIN_ID = "plugin.video.hdrezka.tv"


class HDRezkaAddon:
    def __init__(self):
        self.addon = xbmcaddon.Addon(PLUGIN_ID)
        self.handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1
        self.plugin_url = sys.argv[0] if len(sys.argv) > 0 else f"plugin://{PLUGIN_ID}/"
        
        self.icon = self.addon.getAddonInfo("icon")
        self.fanart = self.addon.getAddonInfo("fanart")
        self.next_icon = os.path.join(self.addon.getAddonInfo("path"), "resources", "icons", "next.png")

        # Load settings
        self.domain = self.addon.getSetting("domain") or "kinopub.me"
        self.protocol = self.addon.getSetting("dom_protocol") or "https"
        self.quality_pref = self.addon.getSetting("quality") or "select"
        self.translator_pref = self.addon.getSetting("translator") or "select"
        self.fetch_description = self.addon.getSettingBool("description") if hasattr(self.addon, "getSettingBool") else (self.addon.getSetting("description") != "false")

        # Proxy settings
        use_proxy = self.addon.getSettingBool("use_proxy") if hasattr(self.addon, "getSettingBool") else (self.addon.getSetting("use_proxy") == "true")
        proxy_proto = self.addon.getSetting("protocol") or "http"
        proxy_url = self.addon.getSetting("proxy_url") or ""
        proxy_config = {
            "use_proxy": use_proxy,
            "protocol": proxy_proto,
            "proxy_url": proxy_url
        }

        # Initialize smart client
        self.client = RezkaClient(
            domain=self.domain,
            protocol=self.protocol,
            proxy_config=proxy_config,
            user_agent=DEFAULT_USER_AGENT
        )

        # Check account authorization if enabled
        auth_enabled = self.addon.getSettingBool("auth_enabled") if hasattr(self.addon, "getSettingBool") else (self.addon.getSetting("auth_enabled") == "true")
        if auth_enabled and not self.client.is_logged_in():
            username = self.addon.getSetting("username")
            password = self.addon.getSetting("password")
            if username and password:
                log("Auto-authenticating with saved credentials...")
                self.client.login(username, password)

    def get_string(self, string_id):
        return self.addon.getLocalizedString(string_id)

    def normalize_url(self, raw_url):
        """
        Normalizes any URL (e.g. from an old favorite using a legacy domain)
        to the currently active mirror domain and protocol.
        """
        if not raw_url:
            return self.client.base_url
        parsed = urllib.parse.urlparse(raw_url)
        path = parsed.path
        if parsed.query:
            path += f"?{parsed.query}"
        return f"{self.client.base_url}/{path.lstrip('/')}"

    def build_uri(self, mode, **kwargs):
        params = {"mode": mode}
        for k, v in kwargs.items():
            if v is not None:
                params[k] = str(v)
        return f"{self.plugin_url}?{urllib.parse.urlencode(params)}"

    def run(self):
        query_string = sys.argv[2][1:] if len(sys.argv) > 2 and sys.argv[2].startswith("?") else ""
        params = dict(urllib.parse.parse_qsl(query_string))
        mode = params.get("mode")

        log(f"Handling mode='{mode}' with params: {params}")

        if not mode:
            self.show_main_menu()
        elif mode == "show":
            self.show_item(params.get("url"))
        elif mode == "play":
            self.play_stream(params.get("url"), params.get("title"))
        elif mode == "play_episode":
            self.play_episode(params)
        elif mode == "index":
            url = params.get("url", f"{self.client.base_url}/films/")
            page = int(params.get("page", 1))
            self.show_catalog(url, page)
        elif mode == "categories":
            self.show_categories()
        elif mode == "sub_categories":
            self.show_sub_categories(params.get("url"))
        elif mode == "collections":
            page = int(params.get("page", 1))
            self.show_collections(page)
        elif mode == "search":
            self.show_search(params.get("keyword"))
        elif mode == "history":
            self.show_history()
        elif mode == "clear_history":
            clear_history()
            xbmcgui.Dialog().notification("HDRezka", self.get_string(30009), self.icon, 2000)
            xbmc.executebuiltin("Container.Refresh")
        elif mode == "favorites":
            self.show_favorites(int(params.get("page", 1)))
        elif mode == "login_action":
            self.action_login()
        else:
            log(f"Unknown mode: {mode}, opening main menu")
            self.show_main_menu()

    # -------------------------------------------------------------------------
    # Main Menu & Navigation
    # -------------------------------------------------------------------------
    def show_main_menu(self):
        items = [
            (30000, "search", self.icon),
            (30001, "history", self.icon),
        ]

        # If user has enabled account or is logged in, show Bookmarks
        auth_enabled = self.addon.getSettingBool("auth_enabled") if hasattr(self.addon, "getSettingBool") else (self.addon.getSetting("auth_enabled") == "true")
        if auth_enabled or self.client.is_logged_in():
            items.append((30003, "favorites", self.icon))

        items.extend([
            (30004, "films", self.icon),
            (30005, "series", self.icon),
            (30006, "cartoons", self.icon),
            (30007, "animation", self.icon),
            (30002, "categories", self.icon),
            (30008, "collections", self.icon),
        ])

        for str_id, section, thumb in items:
            title = self.get_string(str_id)
            if section in ("films", "series", "cartoons", "animation"):
                uri = self.build_uri("index", url=f"{self.client.base_url}/{section}/", page=1)
            elif section == "categories":
                uri = self.build_uri("categories")
            elif section == "collections":
                uri = self.build_uri("collections", page=1)
            elif section == "search":
                uri = self.build_uri("search")
            elif section == "history":
                uri = self.build_uri("history")
            elif section == "favorites":
                uri = self.build_uri("favorites", page=1)
            else:
                uri = self.build_uri(section)

            item = xbmcgui.ListItem(title)
            set_art(item, {"icon": thumb, "thumb": thumb, "fanart": self.fanart})
            xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=True)

        xbmcplugin.setContent(self.handle, "files")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    def show_catalog(self, url, page=1):
        url = self.normalize_url(url)
        page_url = url.rstrip("/")
        if page > 1:
            page_url = f"{page_url}/page/{page}/"
        else:
            page_url = f"{page_url}/"

        log(f"Fetching catalog: {page_url}")
        try:
            html = self.client.request(page_url)
        except Exception as e:
            xbmcgui.Dialog().notification("HDRezka", f"Ошибка загрузки: {e}", self.icon, 3000)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return

        items = parse_catalog_items(html, self.client.base_url)
        for entry in items:
            title = entry["title"]
            rating_str = f" [COLOR=green][{entry['rating']}][/COLOR]" if entry["rating"] else ""
            year_str = f" [COLOR=gray]({entry['extra_info']})[/COLOR]" if entry["extra_info"] else ""
            display_title = f"{title}{rating_str}{year_str}"

            uri = self.build_uri("show", url=entry["url"])
            item = xbmcgui.ListItem(display_title)
            
            info = {
                "title": title,
                "year": entry["year"],
                "country": entry["country"],
                "genre": entry["genre"],
                "rating": entry["rating"],
                "mediatype": "tvshow" if entry["is_serial"] else "movie",
            }
            set_video_info(item, info)
            set_art(item, {
                "icon": entry["image"] or self.icon,
                "thumb": entry["image"] or self.icon,
                "poster": entry["image"] or self.icon,
                "fanart": self.fanart
            })

            # If movie and quality preference is preset (not 'select'), it can be directly playable
            if not entry["is_serial"] and self.quality_pref != "select":
                item.setProperty("IsPlayable", "true")
                xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=False)
            else:
                xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=True)

        # Pagination: check if there's a next page
        if len(items) >= 16:
            next_title = f"[COLOR=orange]{self.get_string(1004)}[/COLOR]"
            next_uri = self.build_uri("index", url=url, page=page + 1)
            next_item = xbmcgui.ListItem(next_title)
            set_art(next_item, {"icon": self.next_icon, "thumb": self.next_icon, "fanart": self.fanart})
            xbmcplugin.addDirectoryItem(self.handle, next_uri, next_item, isFolder=True)

        xbmcplugin.setContent(self.handle, "movies")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    def show_categories(self):
        log("Loading categories")
        try:
            html = self.client.request(self.client.base_url)
        except Exception as e:
            xbmcgui.Dialog().notification("HDRezka", f"Ошибка: {e}", self.icon, 3000)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return

        genres = parse_dom(html, "ul", attrs={"id": "topnav-menu"})
        if genres:
            titles = parse_dom(genres[0], "a", attrs={"class": "b-topnav__item-link"})
            links = parse_dom(genres[0], "a", attrs={"class": "b-topnav__item-link"}, ret="href")
            for i, name in enumerate(titles):
                title = strip_tags(name)
                link = self.normalize_url(links[i])
                uri = self.build_uri("sub_categories", url=link)
                item = xbmcgui.ListItem(title)
                set_art(item, {"icon": self.icon, "thumb": self.icon, "fanart": self.fanart})
                xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=True)

        xbmcplugin.setContent(self.handle, "files")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    def show_sub_categories(self, url):
        url = self.normalize_url(url)
        try:
            html = self.client.request(url)
        except Exception as e:
            xbmcgui.Dialog().notification("HDRezka", f"Ошибка: {e}", self.icon, 3000)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return

        # Add link to all items in category
        root_title = f"[COLOR=lightblue][ {self.get_string(1007)} ][/COLOR]"
        root_uri = self.build_uri("index", url=url, page=1)
        root_item = xbmcgui.ListItem(root_title)
        set_art(root_item, {"icon": self.icon, "thumb": self.icon, "fanart": self.fanart})
        xbmcplugin.addDirectoryItem(self.handle, root_uri, root_item, isFolder=True)

        genres = parse_dom(html, "ul", attrs={"class": "left"})
        if genres:
            titles = parse_dom(genres[0], "a")
            links = parse_dom(genres[0], "a", ret="href")
            clean_url = url.replace(self.client.base_url, "")
            for i, title in enumerate(titles):
                if not links[i].startswith(clean_url):
                    continue
                sub_url = self.normalize_url(links[i])
                uri = self.build_uri("index", url=sub_url, page=1)
                item = xbmcgui.ListItem(strip_tags(title))
                set_art(item, {"icon": self.icon, "thumb": self.icon, "fanart": self.fanart})
                xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=True)

        xbmcplugin.setContent(self.handle, "files")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    def show_collections(self, page=1):
        col_url = f"{self.client.base_url}/collections/"
        if page > 1:
            col_url = f"{col_url}page/{page}/"

        try:
            html = self.client.request(col_url)
        except Exception as e:
            xbmcgui.Dialog().notification("HDRezka", f"Ошибка: {e}", self.icon, 3000)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return

        content = parse_dom(html, "div", attrs={"class": "b-content__collections_list"})
        if content:
            titles = parse_dom(content[0], "a", attrs={"class": "title"})
            counts = parse_dom(content[0], "div", attrs={"class": "num"})
            links = parse_dom(content[0], "div", attrs={"class": "b-content__collections_item"}, ret="data-url")
            covers = parse_dom(content[0], "img", attrs={"class": "cover"}, ret="src")

            for i, name in enumerate(titles):
                link = self.normalize_url(links[i]) if i < len(links) else ""
                cnt = counts[i] if i < len(counts) else ""
                cover = covers[i] if i < len(covers) else self.icon
                title = f"{name} [COLOR=gray]({cnt})[/COLOR]"

                uri = self.build_uri("index", url=link, page=1)
                item = xbmcgui.ListItem(title)
                set_art(item, {"icon": cover, "thumb": cover, "fanart": self.fanart})
                xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=True)

            if len(titles) >= 32:
                next_uri = self.build_uri("collections", page=page + 1)
                next_item = xbmcgui.ListItem(self.get_string(1004))
                set_art(next_item, {"icon": self.next_icon, "thumb": self.next_icon, "fanart": self.fanart})
                xbmcplugin.addDirectoryItem(self.handle, next_uri, next_item, isFolder=True)

        xbmcplugin.setContent(self.handle, "files")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    # -------------------------------------------------------------------------
    # Search & History
    # -------------------------------------------------------------------------
    def show_search(self, keyword=None):
        if not keyword:
            kbd = xbmc.Keyboard("", self.get_string(30000))
            kbd.doModal()
            if not kbd.isConfirmed():
                return
            keyword = kbd.getText().strip()
            if not keyword:
                return

        add_to_history(keyword)
        search_url = f"{self.client.base_url}/search/?do=search&subaction=search&q={urllib.parse.quote(keyword)}"
        self.show_catalog(search_url, page=1)

    def show_history(self):
        history_items = get_history()
        
        # Option to clear history
        if history_items:
            clear_uri = self.build_uri("clear_history")
            clear_item = xbmcgui.ListItem(f"[COLOR=red]{self.get_string(30009)}[/COLOR]")
            set_art(clear_item, {"icon": self.icon, "thumb": self.icon, "fanart": self.fanart})
            xbmcplugin.addDirectoryItem(self.handle, clear_uri, clear_item, isFolder=False)

        for word in history_items:
            uri = self.build_uri("search", keyword=word)
            item = xbmcgui.ListItem(word)
            set_art(item, {"icon": self.icon, "thumb": self.icon, "fanart": self.fanart})
            xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=True)

        xbmcplugin.setContent(self.handle, "files")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    # -------------------------------------------------------------------------
    # Account Bookmarks (Favorites on site)
    # -------------------------------------------------------------------------
    def show_favorites(self, page=1):
        if not self.client.is_logged_in():
            # Prompt login
            dialog = xbmcgui.Dialog()
            if dialog.yesno("HDRezka", "Для доступа к закладкам необходима авторизация. Выполнить вход сейчас?"):
                self.action_login()
            else:
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

        fav_url = f"{self.client.base_url}/favorites/"
        if page > 1:
            fav_url = f"{fav_url}page/{page}/"

        self.show_catalog(fav_url, page=page)

    def action_login(self):
        username = self.addon.getSetting("username")
        password = self.addon.getSetting("password")
        if not username or not password:
            d = xbmcgui.Dialog()
            username = d.input("Введите логин или email", defaultt=username)
            if not username:
                return
            password = d.input("Введите пароль", defaultt=password, type=xbmcgui.INPUT_ALPHANUM, option=xbmcgui.ALPHANUM_HIDE_INPUT)
            if not password:
                return
            self.addon.setSetting("username", username)
            self.addon.setSetting("password", password)
            self.addon.setSetting("auth_enabled", "true")

        success, msg = self.client.login(username, password)
        dialog = xbmcgui.Dialog()
        if success:
            dialog.notification("HDRezka", self.get_string(30012), self.icon, 3000)
        else:
            dialog.ok("HDRezka", f"{self.get_string(30013)}:\n{msg}")

    # -------------------------------------------------------------------------
    # Show Page (Movie details or Episodes list)
    # -------------------------------------------------------------------------
    def show_item(self, url):
        url = self.normalize_url(url)
        log(f"Showing item: {url}")
        try:
            html = self.client.request(url)
        except Exception as e:
            xbmcgui.Dialog().notification("HDRezka", f"Ошибка: {e}", self.icon, 3000)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return

        post_id_match = re.findall(r'id=[\'"]post_id[\'"]\s+value=[\'"](\d+)[\'"]', html)
        if not post_id_match:
            post_id_match = re.findall(r'value=[\'"](\d+)[\'"]\s+id=[\'"]post_id[\'"]', html)
        if not post_id_match:
            post_id_match = re.findall(r'/(\d+)-[^\/]+\.html', url)
        post_id = post_id_match[0] if post_id_match else None
        
        main_titles = parse_dom(html, "h1")
        main_title = strip_tags(main_titles[0]) if main_titles else "Video"

        covers = parse_dom(html, "img", attrs={"itemprop": "image"}, ret="src")
        poster = covers[0] if covers else self.icon
        if not poster.startswith("http"):
            poster = f"{self.client.base_url}/{poster.lstrip('/')}"

        translators = parse_translators(html)
        active_translator_id = "0"
        for t in translators:
            if t["active"]:
                active_translator_id = t["id"]
                break
        if active_translator_id == "0" and translators:
            active_translator_id = translators[0]["id"]
        
        # If still "0", try to get default translator from initCDNSeriesEvents or initCDNMoviesEvents
        if active_translator_id == "0":
            init_s = re.search(r'initCDNSeriesEvents\s*\(\s*\d+\s*,\s*(\d+)', html)
            init_m = re.search(r'initCDNMoviesEvents\s*\(\s*\d+\s*,\s*(\d+)', html)
            if init_s:
                active_translator_id = init_s.group(1)
            elif init_m:
                active_translator_id = init_m.group(1)

        # Check if TV Series (has seasons / episodes)
        is_series = (
            "/series/" in url
            or "simple-episodes-tabs" in html
            or "simple-episodes-list" in html
            or "initCDNSeriesEvents" in html
        )

        if is_series:
            self._handle_series(html, url, post_id, main_title, poster, translators, active_translator_id)
        else:
            self._handle_movie(html, url, post_id, main_title, poster, translators, active_translator_id)

    def _handle_movie(self, html, url, post_id, title, poster, translators, active_translator_id):
        log(f"Handling movie: {title} (ID: {post_id})")

        # Select translator if multiple and requested
        chosen_tid = active_translator_id
        if len(translators) > 1 and self.translator_pref == "select":
            t_names = [t["name"] for t in translators]
            idx = xbmcgui.Dialog().select(self.get_string(30010), t_names)
            if idx >= 0:
                chosen_tid = translators[idx]["id"]

        raw_url = ""
        subtitles = []

        # If translator is unchanged and page already has embedded streams in HTML, extract directly
        if chosen_tid == active_translator_id:
            m_streams = re.search(r'\"streams\":\s*\"([^\"]+)\"', html)
            if m_streams:
                raw_url = m_streams.group(1).replace(r"\/", "/")
                log("Extracted movie streams directly from page HTML")

        # If not embedded or a different translator was selected, request via AJAX
        if not raw_url:
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": url,
                "Origin": self.client.base_url
            }
            data = {
                "id": post_id,
                "translator_id": chosen_tid,
                "action": "get_movie"
            }
            ajax_url = f"{self.client.base_url}/ajax/get_cdn_series/"

            try:
                resp_str = self.client.request(ajax_url, data=data, headers=headers)
                res = json.loads(resp_str)
                if not res.get("success"):
                    msg = res.get("message", "Ошибка получения видео")
                    log(f"get_movie returned success=False: {msg}")
                    xbmcgui.Dialog().notification("HDRezka", msg, self.icon, 3000)
                    xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                    return
                raw_url = res.get("url", "")
                subtitles = parse_subtitles(res)
            except Exception as e:
                log(f"Failed to fetch movie stream AJAX: {e}")
                xbmcgui.Dialog().notification("HDRezka", f"Ошибка получения видео: {e}", self.icon, 3000)
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

        links = parse_stream_links(raw_url)
        if not links:
            xbmcgui.Dialog().ok("HDRezka", "Не удалось найти ссылки на видео.")
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return

        # If quality preference is "select" and multiple streams available, list them in the directory
        if self.quality_pref == "select" and len(links) > 1:
            for q in sorted(links.keys(), key=lambda k: QUALITY_WEIGHTS.get(k, 0), reverse=True):
                q_link = links[q]
                q_title = f"{title} ({q})"
                q_uri = self.build_uri("play", url=q_link, title=q_title)
                q_item = xbmcgui.ListItem(q_title)
                set_video_info(q_item, {"title": q_title, "mediatype": "movie"})
                set_art(q_item, {"icon": poster, "thumb": poster, "poster": poster, "fanart": self.fanart})
                q_item.setProperty("IsPlayable", "true")
                if subtitles:
                    sub_urls = [s["url"] for s in subtitles if s.get("url")]
                    if sub_urls:
                        q_item.setSubtitles(sub_urls)
                xbmcplugin.addDirectoryItem(self.handle, q_uri, q_item, isFolder=False)

            xbmcplugin.setContent(self.handle, "movies")
            xbmcplugin.endOfDirectory(self.handle, succeeded=True)
            return

        self._choose_quality_and_play(links, title, poster, subtitles)

    def _handle_series(self, html, url, post_id, main_title, poster, translators, active_translator_id):
        log(f"Handling series: {main_title} (ID: {post_id})")

        chosen_tid = active_translator_id
        if len(translators) > 1 and self.translator_pref == "select":
            t_names = [t["name"] for t in translators]
            idx = xbmcgui.Dialog().select(self.get_string(30010), t_names)
            if idx >= 0:
                chosen_tid = translators[idx]["id"]

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": url,
            "Origin": self.client.base_url
        }
        data = {
            "id": post_id,
            "translator_id": chosen_tid,
            "action": "get_episodes"
        }
        ajax_url = f"{self.client.base_url}/ajax/get_cdn_series/"

        try:
            resp_str = self.client.request(ajax_url, data=data, headers=headers)
            res = json.loads(resp_str)
            episodes_html = res.get("episodes", "")
        except Exception as e:
            log(f"Failed to fetch episodes AJAX, falling back to page DOM: {e}")
            episodes_html = html

        # Parse all episodes across all seasons
        episodes = []
        for m in re.finditer(r'<li\b([^>]*)>(.*?)</li>', episodes_html, re.DOTALL | re.IGNORECASE):
            attrs_str, content = m.group(1), m.group(2)
            ep_m = re.search(r'data-episode_id=[\'"](\d+)[\'"]', attrs_str)
            if not ep_m:
                continue
            e_num = ep_m.group(1)
            s_m = re.search(r'data-season_id=[\'"](\d+)[\'"]', attrs_str)
            s_num = s_m.group(1) if s_m else "1"
            id_m = re.search(r'data-id=[\'"](\d+)[\'"]', attrs_str)
            p_id = id_m.group(1) if id_m else post_id
            cdn_m = re.search(r'data-cdn_url=[\'"]([^\'"]*)[\'"]', attrs_str)
            cdn_url = cdn_m.group(1) if cdn_m else ""
            ep_title = strip_tags(content)
            episodes.append((s_num, e_num, p_id, ep_title, cdn_url))

        # Fallback if regex didn't find items
        if not episodes:
            li_items = parse_dom(episodes_html, "li")
            ids = parse_dom(episodes_html, "li", ret="data-id")
            seasons = parse_dom(episodes_html, "li", ret="data-season_id")
            episodes_nums = parse_dom(episodes_html, "li", ret="data-episode_id")
            cdn_urls = parse_dom(episodes_html, "li", ret="data-cdn_url")
            for i in range(len(li_items)):
                s_num = seasons[i] if i < len(seasons) else "1"
                e_num = episodes_nums[i] if i < len(episodes_nums) else str(i + 1)
                p_id = ids[i] if i < len(ids) else post_id
                cdn_url = cdn_urls[i] if i < len(cdn_urls) else ""
                episodes.append((s_num, e_num, p_id, strip_tags(li_items[i]), cdn_url))

        for s_num, e_num, item_post_id, ep_title, cdn_url in episodes:
            full_title = f"{main_title} - S{s_num.zfill(2)}E{e_num.zfill(2)} ({ep_title})"
            
            uri = self.build_uri(
                "play_episode",
                url=url,
                post_id=item_post_id,
                season_id=s_num,
                episode_id=e_num,
                title=full_title,
                image=poster,
                idt=chosen_tid,
                data=cdn_url
            )

            item = xbmcgui.ListItem(full_title)
            info = {
                "title": full_title,
                "season": s_num,
                "episode": e_num,
                "mediatype": "episode",
            }
            set_video_info(item, info)
            set_art(item, {"icon": poster, "thumb": poster, "poster": poster, "fanart": self.fanart})
            item.setProperty("IsPlayable", "true")
            xbmcplugin.addDirectoryItem(self.handle, uri, item, isFolder=False)

        xbmcplugin.setContent(self.handle, "episodes")
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    # -------------------------------------------------------------------------
    # Stream Resolving & Playback
    # -------------------------------------------------------------------------
    def play_episode(self, params):
        url = self.normalize_url(params.get("url"))
        post_id = params.get("post_id")
        season_id = params.get("season_id")
        episode_id = params.get("episode_id")
        idt = params.get("idt", "0")
        title = params.get("title", "Episode")
        poster = params.get("image", self.icon)
        data = params.get("data", "")

        # Fallback post_id from url
        if (not post_id or post_id == "None") and url:
            id_m = re.search(r'/(\d+)-[^\/]+\.html', url)
            if id_m:
                post_id = id_m.group(1)

        # Fallback default translator ID
        if not idt or idt in ("0", "None"):
            try:
                page_html = self.client.request(url)
                init_m = re.search(r'initCDNSeriesEvents\s*\(\s*\d+\s*,\s*(\d+)', page_html)
                if init_m:
                    idt = init_m.group(1)
                else:
                    t_list = parse_translators(page_html)
                    if t_list:
                        idt = t_list[0]["id"]
            except Exception as e:
                log(f"Failed to find translator ID for episode: {e}")

        subtitles = []
        if not data or data == "null":
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": url,
                "Origin": self.client.base_url
            }
            req_data = {
                "id": post_id,
                "translator_id": idt,
                "season": season_id,
                "episode": episode_id,
                "action": "get_stream"
            }
            ajax_url = f"{self.client.base_url}/ajax/get_cdn_series/"

            try:
                resp_str = self.client.request(ajax_url, data=req_data, headers=headers)
                res = json.loads(resp_str)
                if not res.get("success"):
                    msg = res.get("message", "Ошибка получения потока")
                    log(f"get_cdn_series returned success=False: {msg}")
                    xbmcgui.Dialog().notification("HDRezka", msg, self.icon, 3000)
                    return
                data = res.get("url", "")
                subtitles = parse_subtitles(res)
            except Exception as e:
                log(f"Error fetching episode stream: {e}")
                xbmcgui.Dialog().notification("HDRezka", f"Ошибка потока: {e}", self.icon, 3000)
                return

        links = parse_stream_links(data)
        if not links:
            xbmcgui.Dialog().ok("HDRezka", "Не удалось извлечь видеопоток серии.")
            return

        self._choose_quality_and_play(links, title, poster, subtitles)

    def _choose_quality_and_play(self, links, title, poster, subtitles=None):
        """Selects quality and resolves stream for playback."""
        # Sort links by quality weight
        sorted_qualities = sorted(links.keys(), key=lambda q: QUALITY_WEIGHTS.get(q, 0), reverse=True)
        if not sorted_qualities:
            xbmcgui.Dialog().ok("HDRezka", "Потоки недоступны.")
            if self.handle > 0:
                xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
            return

        selected_url = None
        if self.quality_pref != "select":
            pref_weight = QUALITY_WEIGHTS.get(self.quality_pref, 999)
            # Find best match <= pref_weight
            for q in sorted_qualities:
                if QUALITY_WEIGHTS.get(q, 0) <= pref_weight:
                    selected_url = links[q]
                    log(f"Auto-selected quality '{q}' based on preference '{self.quality_pref}'")
                    break

        if not selected_url:
            if len(sorted_qualities) == 1:
                selected_url = links[sorted_qualities[0]]
            else:
                dialog = xbmcgui.Dialog()
                idx = dialog.select(self.get_string(30011), sorted_qualities)
                if idx < 0:
                    if self.handle > 0:
                        xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
                    return
                selected_url = links[sorted_qualities[idx]]

        self.play_stream(selected_url, title, subtitles)

    def play_stream(self, stream_url, title=None, subtitles=None):
        """
        Prepares the ListItem with proper headers for Voidboost/CDN and starts playback.
        """
        if not stream_url:
            if self.handle > 0:
                xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
            return

        # Append headers required by Voidboost/CDN for playback without 403 blocks
        headers = {
            "User-Agent": self.client.user_agent,
            "Referer": f"{self.client.base_url}/"
        }
        encoded_headers = urllib.parse.urlencode(headers)
        playback_url = f"{stream_url}|{encoded_headers}"

        log(f"Starting playback for: {playback_url}")

        item = xbmcgui.ListItem(path=playback_url)
        if title:
            item.setLabel(title)
            set_video_info(item, {"title": title})

        # Set MIME type and properties for instant playback without probing
        if ".m3u8" in stream_url:
            item.setMimeType("application/vnd.apple.mpegurl")
            item.setProperty("inputstream", "inputstream.adaptive")
            item.setProperty("inputstream.adaptive.manifest_type", "hls")
        else:
            item.setMimeType("video/mp4")

        item.setContentLookup(False)

        # Attach subtitles if available
        if subtitles:
            sub_urls = [s["url"] for s in subtitles if s.get("url")]
            if sub_urls:
                log(f"Attaching subtitles: {sub_urls}")
                item.setSubtitles(sub_urls)

        if self.handle > 0:
            xbmcplugin.setResolvedUrl(self.handle, succeeded=True, listitem=item)
        else:
            xbmc.Player().play(playback_url, item)


if __name__ == "__main__":
    addon = HDRezkaAddon()
    addon.run()

