#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script to package HDRezka into an installable Kodi add-on zip file.
Output: packages/plugin.video.hdrezka.tv-{version}.zip
"""

import os
import zipfile
import re

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(TOOLS_DIR)
ADDON_ID = "plugin.video.hdrezka.tv"
PACKAGES_DIR = os.path.join(BASE_DIR, "packages")


def get_version():
    addon_xml = os.path.join(BASE_DIR, "addon.xml")
    with open(addon_xml, "r", encoding="utf-8") as f:
        match = re.search(r'id="' + ADDON_ID + r'"\s+name="[^"]*"\s+version="([^"]+)"', f.read())
        if match:
            return match.group(1)
    return "3.3.2"


def build():
    version = get_version()
    os.makedirs(PACKAGES_DIR, exist_ok=True)
    zip_name = f"{ADDON_ID}-{version}.zip"
    zip_path = os.path.join(PACKAGES_DIR, zip_name)

    exclude_dirs = {".git", ".idea", "__pycache__", ".vscode", "repo", "repository.hdrezka", "packages", "tools"}
    exclude_exts = {".pyc", ".pyo", ".DS_Store", ".zip"}

    print(f"Building {zip_name} into packages/...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(BASE_DIR):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if any(file.endswith(ext) for ext in exclude_exts):
                    continue
                if file in (".gitignore",):
                    continue

                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, BASE_DIR)
                arcname = os.path.join(ADDON_ID, rel_path)
                print(f"  + {arcname}")
                z.write(abs_path, arcname)

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"\nSuccessfully built: {zip_path} ({size_kb:.1f} KB)")
    print(f"Ready to install via 'Install from zip file' in Kodi on Windows and Android!")


if __name__ == "__main__":
    build()

