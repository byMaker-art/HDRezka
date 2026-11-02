# -*- coding: utf-8 -*-
"""
Smart HTTP Client with Anubis Proof-of-Work solver and session management.
"""

import gzip
import hashlib
import http.cookiejar
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .compat import get_profile_path, log

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class RezkaClient:
    def __init__(self, domain="kinopub.me", protocol="https", proxy_config=None, user_agent=None):
        self.domain = domain.strip().replace("https://", "").replace("http://", "").rstrip("/")
        self.protocol = protocol.lower() if protocol in ("http", "https") else "https"
        self.proxy_config = proxy_config or {}
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        
        self.cookie_file = os.path.join(get_profile_path(), "cookies.dat")
        self.cookie_jar = http.cookiejar.LWPCookieJar(self.cookie_file)
        self._load_cookies()
        
        self.opener = self._build_opener()

    @property
    def base_url(self):
        return f"{self.protocol}://{self.domain}"

    def update_settings(self, domain=None, protocol=None, proxy_config=None):
        if domain:
            self.domain = domain.strip().replace("https://", "").replace("http://", "").rstrip("/")
        if protocol:
            self.protocol = protocol.lower() if protocol in ("http", "https") else "https"
        if proxy_config is not None:
            self.proxy_config = proxy_config
        self.opener = self._build_opener()

    def _load_cookies(self):
        try:
            if os.path.exists(self.cookie_file):
                self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
                log(f"Loaded {len(self.cookie_jar)} cookies from cache")
        except Exception as e:
            log(f"Failed to load cookies: {e}")

    def save_cookies(self):
        try:
            self.cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            log(f"Failed to save cookies: {e}")

    def _build_opener(self):
        handlers = [urllib.request.HTTPCookieProcessor(self.cookie_jar)]

        # Proxy handling
        if self.proxy_config.get("use_proxy") and self.proxy_config.get("proxy_url"):
            proto = self.proxy_config.get("protocol", "http").lower()
            proxy_url = self.proxy_config.get("proxy_url").strip()
            if not proxy_url.startswith("http://") and not proxy_url.startswith("https://") and not proxy_url.startswith("socks5://"):
                proxy_url = f"{proto}://{proxy_url}"
            
            log(f"Configuring proxy: {proto} -> {proxy_url}")
            if proto == "socks5":
                try:
                    # In case PySocks / socks is available
                    import socks
                    from sockshandler import SocksiPyHandler
                    handlers.append(SocksiPyHandler(socks.PROXY_TYPE_SOCKS5, proxy_url))
                except ImportError:
                    log("PySocks not installed, trying standard urllib proxy handler")
                    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
                    handlers.append(proxy_handler)
            else:
                proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
                handlers.append(proxy_handler)

        # SSL context (disable unneeded verification hurdles on some Android boxes if certificates are outdated)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        except Exception:
            pass

        return urllib.request.build_opener(*handlers)

    def request(self, url, data=None, headers=None, referer=None, max_anubis_retries=2):
        """
        Executes HTTP GET/POST with automatic decompression and Anubis PoW solving.
        """
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"{self.base_url}/{url.lstrip('/')}"

        # Standard browser headers
        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Host": urllib.parse.urlparse(url).netloc or self.domain,
        }

        if referer:
            req_headers["Referer"] = referer
        elif url != self.base_url:
            req_headers["Referer"] = f"{self.base_url}/"

        if headers:
            req_headers.update(headers)

        encoded_data = None
        if data is not None:
            if isinstance(data, dict):
                encoded_data = urllib.parse.urlencode(data).encode("utf-8")
                if "Content-Type" not in req_headers:
                    req_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            elif isinstance(data, str):
                encoded_data = data.encode("utf-8")
            else:
                encoded_data = data

        req = urllib.request.Request(url, data=encoded_data, headers=req_headers)

        try:
            resp = self.opener.open(req, timeout=30)
            raw_content = resp.read()
            content_encoding = resp.headers.get("Content-Encoding", "").lower()

            if content_encoding == "gzip" or raw_content[:2] == b"\x1f\x8b":
                html = gzip.decompress(raw_content).decode("utf-8", errors="ignore")
            elif content_encoding == "deflate":
                import zlib
                try:
                    html = zlib.decompress(raw_content).decode("utf-8", errors="ignore")
                except Exception:
                    html = zlib.decompress(raw_content, -zlib.MAX_WBITS).decode("utf-8", errors="ignore")
            else:
                html = raw_content.decode("utf-8", errors="ignore")

            # Check if Anubis challenge is present
            if self._is_anubis_challenge(html):
                if max_anubis_retries > 0:
                    log("Anubis Anti-Bot protection detected! Solving challenge...")
                    solved = self._solve_anubis(html, url)
                    if solved:
                        self.save_cookies()
                        # Retry original request with freshly acquired cookies
                        return self.request(
                            url,
                            data=data,
                            headers=headers,
                            referer=referer,
                            max_anubis_retries=max_anubis_retries - 1
                        )
                    else:
                        log("Failed to solve Anubis challenge")
                else:
                    log("Max Anubis challenge retries exceeded")

            self.save_cookies()
            return html

        except urllib.error.HTTPError as e:
            log(f"HTTPError: {e.code} for URL {url}")
            try:
                error_body = e.read()
                if e.headers.get("Content-Encoding") == "gzip" or error_body[:2] == b"\x1f\x8b":
                    html = gzip.decompress(error_body).decode("utf-8", errors="ignore")
                else:
                    html = error_body.decode("utf-8", errors="ignore")
                
                if self._is_anubis_challenge(html) and max_anubis_retries > 0:
                    log("Anubis Anti-Bot challenge in HTTP error page! Solving...")
                    if self._solve_anubis(html, url):
                        self.save_cookies()
                        return self.request(
                            url,
                            data=data,
                            headers=headers,
                            referer=referer,
                            max_anubis_retries=max_anubis_retries - 1
                        )
            except Exception as inner_e:
                log(f"Error handling HTTPError body: {inner_e}")
            raise

        except Exception as e:
            log(f"Request failed for {url}: {e}")
            raise

    def _is_anubis_challenge(self, html):
        """Checks if response contains the Anubis Anti-Bot challenge."""
        if not html:
            return False
        return (
            '<script id="anubis_challenge"' in html
            or 'id="anubis-main"' in html
            or ("Проверяем, что вы не бот!" in html and "anubis" in html.lower())
        )

    def _solve_anubis(self, html, original_url):
        """
        Solves the Anubis Proof-of-Work challenge in Python and submits the solution.
        """
        match = re.search(r'<script id="anubis_challenge" type="application/json">(.*?)</script>', html, re.DOTALL)
        if not match:
            log("Could not find anubis_challenge JSON script tag")
            return False

        try:
            data = json.loads(match.group(1).strip())
            challenge = data["challenge"]
            rules = data["rules"]

            random_data = challenge["randomData"]
            challenge_id = challenge["id"]
            difficulty = rules.get("difficulty", 2)
            
            log(f"Anubis challenge: id={challenge_id}, difficulty={difficulty}")

            p = difficulty // 2
            u = (difficulty % 2) != 0

            nonce = 0
            t_start = time.time()
            found_hash = None

            while True:
                candidate = (random_data + str(nonce)).encode("utf-8")
                h = hashlib.sha256(candidate).digest()

                is_valid = True
                for b in h[:p]:
                    if b != 0:
                        is_valid = False
                        break

                if is_valid and u and (h[p] >> 4 != 0):
                    is_valid = False

                if is_valid:
                    found_hash = h.hex()
                    break

                nonce += 1
                if nonce > 20000000:
                    log("Exceeded maximum nonce iterations for PoW")
                    return False

            elapsed_ms = max(int((time.time() - t_start) * 1000), 150)
            log(f"Anubis PoW solved in {elapsed_ms}ms! Nonce: {nonce}, Hash: {found_hash}")

            parsed = urllib.parse.urlparse(original_url)
            redir_path = parsed.path
            if parsed.query:
                redir_path += f"?{parsed.query}"
            if not redir_path:
                redir_path = "/"

            base_host = f"{parsed.scheme or self.protocol}://{parsed.netloc or self.domain}"
            pass_url = (
                f"{base_host}/.within.website/x/cmd/anubis/api/pass-challenge"
                f"?id={urllib.parse.quote(challenge_id)}"
                f"&response={urllib.parse.quote(found_hash)}"
                f"&nonce={nonce}"
                f"&redir={urllib.parse.quote(redir_path)}"
                f"&elapsedTime={elapsed_ms}"
            )

            pass_headers = {
                "User-Agent": self.user_agent,
                "Referer": original_url,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            pass_req = urllib.request.Request(pass_url, headers=pass_headers)
            pass_resp = self.opener.open(pass_req, timeout=15)
            log(f"Anubis pass-challenge response: {pass_resp.status}")
            return True

        except Exception as e:
            log(f"Error while solving Anubis PoW: {e}")
            return False

    def login(self, username, password):
        """
        Authenticates with HDRezka using username and password.
        Returns tuple (success: bool, message: str)
        """
        if not username or not password:
            return False, "Логин и пароль не могут быть пустыми"

        log(f"Attempting login for user: {username}")
        # First ensure we have valid session cookies / passed Anubis
        try:
            self.request(self.base_url)
        except Exception as e:
            log(f"Failed to access main page before login: {e}")

        login_url = f"{self.base_url}/ajax/login/"
        post_data = {
            "login_name": username.strip(),
            "login_password": password.strip(),
            "login_not_save": "0"
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/",
            "Origin": self.base_url,
        }

        try:
            resp_text = self.request(login_url, data=post_data, headers=headers)
            res = json.loads(resp_text)
            if res.get("success"):
                log("Login successful!")
                self.save_cookies()
                return True, "Успешный вход!"
            else:
                msg = res.get("message", "Неверный логин или пароль")
                log(f"Login failed: {msg}")
                return False, msg
        except Exception as e:
            log(f"Login request error: {e}")
            return False, str(e)

    def is_logged_in(self):
        """Checks if the user has an active session."""
        for cookie in self.cookie_jar:
            if cookie.name in ("dle_user_id", "dle_user_token") and cookie.value:
                return True
        return False

