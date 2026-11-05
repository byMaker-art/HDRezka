#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script to package HDRezka and its repository into an installable Kodi add-on repository.
Generates:
  - packages/plugin.video.hdrezka.tv-{version}.zip
  - packages/repository.hdrezka-1.0.0.zip
  - repo/addons.xml
  - repo/addons.xml.md5
  - repo/zips/...
"""

import os
import zipfile
import re
import hashlib
import shutil

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(TOOLS_DIR)
ADDON_ID = "plugin.video.hdrezka.tv"
REPO_ID = "repository.hdrezka"
PACKAGES_DIR = os.path.join(BASE_DIR, "packages")
REPO_DIR = os.path.join(BASE_DIR, "repo")
ZIPS_DIR = os.path.join(REPO_DIR, "zips")


def get_version(xml_path, addon_id):
    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()
        m = re.search(r'id="' + addon_id + r'"\s+name="[^"]*"\s+version="([^"]+)"', content)
        if m:
            return m.group(1)
    return "1.0.0"


def zip_addon(addon_root, addon_id, target_zip, exclude_dirs=None, exclude_files=None):
    if exclude_dirs is None:
        exclude_dirs = {".git", ".idea", "__pycache__", ".vscode", "repo", "repository.hdrezka", "packages", "tools"}
    if exclude_files is None:
        exclude_files = {".DS_Store", ".gitignore"}

    exclude_exts = {".pyc", ".pyo", ".zip"}

    os.makedirs(os.path.dirname(target_zip), exist_ok=True)
    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(addon_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if any(file.endswith(ext) for ext in exclude_exts):
                    continue
                if file in exclude_files:
                    continue

                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, addon_root)
                arcname = os.path.join(addon_id, rel_path)
                z.write(abs_path, arcname)


def clean_addon_xml(xml_content):
    content = re.sub(r'<\?xml[^>]*\?>', '', xml_content)
    return content.strip()


def build_all():
    print("=== Building HDRezka and Kodi Repository ===")
    os.makedirs(ZIPS_DIR, exist_ok=True)
    os.makedirs(PACKAGES_DIR, exist_ok=True)

    # 1. Version extraction
    plugin_xml = os.path.join(BASE_DIR, "addon.xml")
    plugin_ver = get_version(plugin_xml, ADDON_ID)
    repo_xml = os.path.join(BASE_DIR, REPO_ID, "addon.xml")
    repo_ver = get_version(repo_xml, REPO_ID)

    print(f"Plugin version: {plugin_ver}")
    print(f"Repo version:   {repo_ver}")

    # 2. Build plugin zip in repo/zips and packages/
    plugin_zip_name = f"{ADDON_ID}-{plugin_ver}.zip"
    plugin_repo_zip = os.path.join(ZIPS_DIR, ADDON_ID, plugin_zip_name)
    plugin_pkg_zip = os.path.join(PACKAGES_DIR, plugin_zip_name)

    print(f"\nBuilding {plugin_zip_name}...")
    zip_addon(BASE_DIR, ADDON_ID, plugin_repo_zip)
    shutil.copy2(plugin_repo_zip, plugin_pkg_zip)
    shutil.copy2(os.path.join(BASE_DIR, "icon.png"), os.path.join(ZIPS_DIR, ADDON_ID, "icon.png"))
    shutil.copy2(os.path.join(BASE_DIR, "fanart.jpg"), os.path.join(ZIPS_DIR, ADDON_ID, "fanart.jpg"))
    shutil.copy2(os.path.join(BASE_DIR, "changelog.txt"), os.path.join(ZIPS_DIR, ADDON_ID, f"changelog-{plugin_ver}.txt"))

    # 3. Build repository zip
    repo_zip_name = f"{REPO_ID}-{repo_ver}.zip"
    repo_repo_zip = os.path.join(ZIPS_DIR, REPO_ID, repo_zip_name)
    repo_pkg_zip = os.path.join(PACKAGES_DIR, repo_zip_name)

    print(f"Building {repo_zip_name}...")
    zip_addon(
        os.path.join(BASE_DIR, REPO_ID),
        REPO_ID,
        repo_repo_zip,
        exclude_dirs={".git", "__pycache__"},
        exclude_files={".DS_Store"}
    )
    shutil.copy2(repo_repo_zip, repo_pkg_zip)
    shutil.copy2(os.path.join(BASE_DIR, REPO_ID, "icon.png"), os.path.join(ZIPS_DIR, REPO_ID, "icon.png"))

    # 4. Generate addons.xml
    with open(plugin_xml, "r", encoding="utf-8") as f:
        clean_plugin = clean_addon_xml(f.read())
    with open(repo_xml, "r", encoding="utf-8") as f:
        clean_repo = clean_addon_xml(f.read())

    addons_xml_content = f'<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n{clean_plugin}\n{clean_repo}\n</addons>\n'
    addons_xml_path = os.path.join(REPO_DIR, "addons.xml")
    with open(addons_xml_path, "w", encoding="utf-8") as f:
        f.write(addons_xml_content)

    # 5. Generate addons.xml.md5
    md5_hash = hashlib.md5(addons_xml_content.encode("utf-8")).hexdigest()
    md5_path = os.path.join(REPO_DIR, "addons.xml.md5")
    with open(md5_path, "w", encoding="utf-8") as f:
        f.write(md5_hash)

    print(f"\nGenerated repo/addons.xml")
    print(f"Generated repo/addons.xml.md5 ({md5_hash})")
    print(f"\nArtifacts:")
    print(f"  + {plugin_pkg_zip} ({os.path.getsize(plugin_pkg_zip)/1024:.1f} KB)")
    print(f"  + {repo_pkg_zip} ({os.path.getsize(repo_pkg_zip)/1024:.1f} KB)")
    print(f"  + repo/ directory ready for GitHub hosting!")


if __name__ == "__main__":
    build_all()

