# -*- coding: utf-8 -*-
"""
Search history management.
"""

import json
import os
from .compat import get_profile_path, log

MAX_HISTORY_ITEMS = 30


def _get_history_file():
    return os.path.join(get_profile_path(), "search_history.json")


def get_history():
    """Returns list of past search keywords (most recent first)."""
    fpath = _get_history_file()
    if not os.path.exists(fpath):
        return []
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as e:
        log(f"Error reading search history: {e}")
    return []


def add_to_history(keyword):
    """Adds keyword to the top of search history, removing duplicates."""
    if not keyword or not keyword.strip():
        return
    keyword = keyword.strip()
    history = get_history()
    if keyword in history:
        history.remove(keyword)
    history.insert(0, keyword)
    history = history[:MAX_HISTORY_ITEMS]
    
    fpath = _get_history_file()
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Error saving search history: {e}")


def clear_history():
    """Clears all search history."""
    fpath = _get_history_file()
    try:
        if os.path.exists(fpath):
            os.remove(fpath)
    except Exception as e:
        log(f"Error clearing search history: {e}")
