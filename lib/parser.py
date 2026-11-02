# -*- coding: utf-8 -*-
"""
Rezka HTML and Data Parser.
Pure Python, zero third-party dependencies.
"""

import base64
import html
import re
from itertools import product

QUALITY_WEIGHTS = {
    "360p": 1,
    "480p": 2,
    "720p": 3,
    "1080p": 4,
    "1080p Ultra": 5,
    "2K": 6,
    "4K": 7,
}


def _get_dom_elements(html_text, name, attrs):
    pattern = r"<" + re.escape(name)
    for k, v in attrs.items():
        if k == "class":
            pattern += r'(?=[^>]*?\bclass=[\'"][^\'"]*(?<![^\s\'"])' + re.escape(v) + r'(?![^\s\'"])[^\'"]*[\'"])'
        else:
            pattern += r'(?=[^>]*?\b' + re.escape(k) + r'=(?:[\'"][^\'"]*?' + re.escape(v) + r'[^\'"]*?[\'"]|' + re.escape(v) + r'))'
    pattern += r"[^>]*?>"
    return re.findall(pattern, html_text, re.IGNORECASE | re.DOTALL)


def _get_dom_attributes(tag_str, ret):
    pattern = r'\b' + re.escape(ret) + r'=[\'"]([^\'"]*)[\'"]'
    matches = re.findall(pattern, tag_str, re.IGNORECASE)
    if not matches:
        pattern_no_quote = r'\b' + re.escape(ret) + r'=([^\s>]+)'
        matches = re.findall(pattern_no_quote, tag_str, re.IGNORECASE)
    return [html.unescape(m) for m in matches]


def parse_dom(html_content, name, attrs=None, ret=None):
    """
    Extracts elements or attribute values matching tag and optional attrs.
    Supports nested tags of the same name.
    """
    if not html_content:
        return []
    attrs = attrs or {}
    items = [html_content] if isinstance(html_content, str) else html_content
    result = []
    endstr = "</" + name

    for item in items:
        elements = _get_dom_elements(item, name, attrs)
        if ret:
            for el in elements:
                result.extend(_get_dom_attributes(el, ret))
        else:
            last_idx = 0
            for el in elements:
                start = item.find(el, last_idx)
                if start == -1:
                    start = item.find(el)
                    if start == -1:
                        continue
                end = item.find(endstr, start)
                pos = item.find("<" + name, start + 1)
                while pos < end and pos != -1:
                    tend = item.find(endstr, end + len(endstr))
                    if tend != -1:
                        end = tend
                    pos = item.find("<" + name, pos + 1)
                if start > -1 and end > -1:
                    result.append(item[start + len(el):end])
                    last_idx = end + len(endstr)
    return result


def strip_tags(text):
    """Strips all HTML tags and cleans up whitespace."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def decode_trash_string(raw_str):
    """
    Decodes HDRezka obfuscated stream string if needed.
    """
    if not raw_str:
        return ""
    if raw_str.startswith("[") or "http" in raw_str:
        return raw_str.replace("\\/", "/")

    try:
        trash_set = set()
        trash_list = ["@", "#", "!", "^", "$"]
        for i in range(2, 4):
            for chars in product(trash_list, repeat=i):
                trash_set.add(base64.b64encode("".join(chars).encode("utf-8")).decode("ascii"))

        def decode_trash(s, removelist):
            n = 4
            cleaned = s
            y = 0
            while y < len(s):
                chunk = s[y:y+n]
                if chunk in removelist:
                    cleaned = cleaned.replace(chunk, "", 1)
                else:
                    break
                y += n
            return cleaned

        cleaned_items = []
        raw_items = list(re.split(r"_", re.sub(r"(\/|\\)", "", raw_str)))
        for item in raw_items:
            cleaned_items.append(decode_trash(item, trash_set))

        while len(cleaned_items) > 1:
            combined = cleaned_items[-2] + cleaned_items[-1]
            out = decode_trash(combined, trash_set)
            cleaned_items.pop()
            cleaned_items.pop()
            cleaned_items.append(out)

        decoded = base64.b64decode("".join(cleaned_items).replace("#h", "", 1)).decode("utf-8", errors="ignore")
        return decoded.replace("\\/", "/")
    except Exception:
        return raw_str.replace("\\/", "/")


def parse_stream_links(data_str):
    """
    Parses string like '[360p]https://... or https://...[720p]...'
    Returns dict: {quality: best_stream_url}
    """
    decoded = decode_trash_string(data_str)
    links = {}
    if not decoded:
        return links

    pattern = r"\[([^\]]+)\]([^\[]+)"
    matches = re.findall(pattern, decoded)
    for q, u_str in matches:
        clean_q = strip_tags(q).strip()
        u_str = u_str.rstrip(",").strip()
        options = [u.strip() for u in u_str.split(" or ") if u.strip() and u.strip().startswith("http")]
        if not options:
            continue
        best_url = options[0]
        for opt in options:
            if "manifest.m3u8" in opt or opt.endswith(".m3u8"):
                best_url = opt
                break
        links[clean_q] = best_url

    return links


def parse_subtitles(response_data):
    """
    Extracts subtitle URLs from AJAX response dict or string.
    Returns list of {'lang': str, 'url': str}
    """
    subs = []
    if not response_data:
        return subs

    sub_str = ""
    if isinstance(response_data, dict):
        sub_str = response_data.get("subtitle", "")
    elif isinstance(response_data, str):
        sub_str = response_data

    if not sub_str:
        return subs

    matches = re.findall(r"\[([^\]]+)\](https?://[^\s,\[]+)", sub_str)
    for lang, url in matches:
        subs.append({
            "lang": lang.strip(),
            "url": url.strip().replace("\\/", "/")
        })
    return subs


def parse_catalog_items(html_content, base_url):
    """
    Parses items from Rezka catalog or search result page.
    Returns list of dicts with movie/series info.
    """
    items = []
    if not html_content:
        return items

    # Focus on main container if available to avoid header sliders / duplicate banners
    container = parse_dom(html_content, "div", attrs={"class": "b-content__inline_items"})
    search_context = container[0] if container else html_content

    item_blocks = parse_dom(search_context, "div", attrs={"class": "b-content__inline_item"})
    ids = parse_dom(search_context, "div", attrs={"class": "b-content__inline_item"}, ret="data-id")

    for idx, block in enumerate(item_blocks):
        post_id = ids[idx] if idx < len(ids) else None

        # Title and URL
        link_tag = parse_dom(block, "div", attrs={"class": "b-content__inline_item-link"})
        if not link_tag:
            continue
        
        urls = parse_dom(link_tag[0], "a", ret="href")
        titles = parse_dom(link_tag[0], "a")
        
        if not urls or not titles:
            continue

        raw_url = urls[0]
        if not raw_url.startswith("http"):
            raw_url = f"{base_url}/{raw_url.lstrip('/')}"

        title = strip_tags(titles[0])

        # Extra info (year, country, genre)
        info_divs = parse_dom(link_tag[0], "div")
        info_text = strip_tags(info_divs[0]) if info_divs else ""

        year, country, genre = "", "", ""
        if info_text:
            parts = [p.strip() for p in info_text.split(",") if p.strip()]
            if len(parts) >= 3:
                year, country, genre = parts[0], parts[1], ", ".join(parts[2:])
            elif len(parts) == 2:
                year, genre = parts[0], parts[1]
            elif len(parts) == 1:
                year = parts[0]

        # Poster image (skip flag icons)
        covers = parse_dom(block, "div", attrs={"class": "b-content__inline_item-cover"})
        cover_url = ""
        if covers:
            imgs = parse_dom(covers[0], "img", ret="src")
            for img in imgs:
                if "flag" not in img and "ico" not in img:
                    cover_url = img
                    break
            if not cover_url and imgs:
                cover_url = imgs[0]
            if cover_url and not cover_url.startswith("http"):
                cover_url = f"{base_url}/{cover_url.lstrip('/')}"

        # Is serial?
        is_serial = False
        if "/series/" in raw_url:
            is_serial = True
        elif covers:
            spans = parse_dom(covers[0], "span", attrs={"class": "info"})
            if spans:
                is_serial = True

        # Rating badge
        rating = ""
        rating_spans = parse_dom(block, "span", attrs={"class": "rating"})
        if rating_spans:
            rating = strip_tags(rating_spans[0])

        items.append({
            "post_id": post_id,
            "title": title,
            "url": raw_url,
            "image": cover_url,
            "year": year,
            "country": country,
            "genre": genre,
            "rating": rating,
            "is_serial": is_serial,
            "extra_info": info_text
        })

    return items


def parse_translators(html_content):
    """
    Parses available audio voiceovers / translators.
    Returns list of dicts: {'id': id, 'name': name, 'active': bool, 'director': bool}
    """
    translators = []
    ul_match = re.search(r'<ul\s+id=[\'"]translators-list[\'"][^>]*>(.*?)</ul>', html_content, re.DOTALL | re.IGNORECASE)
    if not ul_match:
        t_matches = re.findall(r'data-translator_id=[\'"](\d+)[\'"][^>]*>(.*?)<', html_content)
        seen = set()
        for t_id, name in t_matches:
            if t_id not in seen:
                seen.add(t_id)
                translators.append({
                    "id": t_id,
                    "name": strip_tags(name),
                    "active": False,
                    "is_director": False
                })
        if not translators:
            init_m = re.search(r'initCDN(?:Movies|Series)Events\s*\(\s*\d+\s*,\s*(\d+)', html_content)
            if init_m:
                translators.append({
                    "id": init_m.group(1),
                    "name": "По умолчанию",
                    "active": True,
                    "is_director": False
                })
        return translators

    ul_html = ul_match.group(1)
    seen = {}
    for m in re.finditer(r'<li\b([^>]*)>(.*?)</li>', ul_html, re.DOTALL | re.IGNORECASE):
        attrs, content = m.group(1), m.group(2)
        full_item = attrs + " " + content
        id_m = re.search(r'data-translator_id=[\'"](\d+)[\'"]', full_item)
        if not id_m:
            continue
        t_id = id_m.group(1)
        title_m = re.search(r'title=[\'"]([^\'"]+)[\'"]', full_item)
        name = title_m.group(1) if title_m else strip_tags(content)
        is_active = "active" in full_item
        is_director = 'data-director="1"' in full_item or "data-director='1'" in full_item
        entry = {
            "id": t_id,
            "name": name.strip(),
            "active": is_active,
            "is_director": is_director
        }
        if t_id not in seen or (not seen[t_id]["active"] and is_active):
            seen[t_id] = entry

    return list(seen.values())


def parse_episodes_from_page(html_content):
    """
    Parses seasons and episodes tabs if embedded directly in page.
    """
    episodes = []
    tabs = parse_dom(html_content, "div", attrs={"id": "simple-episodes-tabs"})
    if not tabs:
        return episodes

    li_items = parse_dom(tabs[0], "li")
    ids = parse_dom(tabs[0], "li", ret="data-id")
    seasons = parse_dom(tabs[0], "li", ret="data-season_id")
    episodes_nums = parse_dom(tabs[0], "li", ret="data-episode_id")
    cdn_urls = parse_dom(tabs[0], "li", ret="data-cdn_url")

    for i in range(len(li_items)):
        title = strip_tags(li_items[i])
        s_id = seasons[i] if i < len(seasons) else "1"
        e_id = episodes_nums[i] if i < len(episodes_nums) else str(i + 1)
        post_id = ids[i] if i < len(ids) else None
        cdn_url = cdn_urls[i] if i < len(cdn_urls) else ""

        episodes.append({
            "title": title,
            "season_id": s_id,
            "episode_id": e_id,
            "post_id": post_id,
            "cdn_url": cdn_url
        })

    return episodes
