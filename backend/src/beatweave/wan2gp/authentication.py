"""WanGP's password-only web login (separate from Gradio auth and MCP OAuth)."""

import json
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

from beatweave.errors import BeatweaveError
from beatweave.wan2gp.schemas import Wan2GPConfig


class _LoginForm(HTMLParser):
    csrf: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("name") == "csrf":
            self.csrf = values.get("value")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward credentials or follow a login redirect to another host.
        return None


class Wan2GPWebSession:
    def __init__(self, config: Wan2GPConfig) -> None:
        self.config = config
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar), _NoRedirect())
        self._authenticated = False

    def authenticate(self) -> dict[str, str]:
        if not self._authenticated:
            login_url = f"{self.config.base_url}/auth/login"
            try:
                with self.opener.open(
                    Request(login_url, headers={"Accept": "text/html"}),
                    timeout=self.config.request_timeout_seconds,
                ) as response:
                    form = _LoginForm()
                    form.feed(response.read().decode("utf-8"))
                if not form.csrf:
                    raise BeatweaveError(
                        "wan2gp_auth_unsupported",
                        "WanGP's password login was not found. Check the URL and --auth setting.",
                    )
                parsed = urlsplit(self.config.base_url)
                request = Request(
                    login_url,
                    data=urlencode(
                        {"csrf": form.csrf, "password": self.config.web_password}
                    ).encode(),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": f"{parsed.scheme}://{parsed.netloc}",
                    },
                )
                try:
                    with self.opener.open(request, timeout=self.config.request_timeout_seconds):
                        pass
                except HTTPError as error:
                    if error.code != 303:
                        raise
                    # WanGP sets its cookie on the successful 303 response.
                    error.close()
                if not any(cookie.name == "wangp_session" for cookie in self.jar):
                    raise BeatweaveError(
                        "wan2gp_auth_failed", "WanGP did not accept the web password."
                    )
                self._authenticated = True
            except HTTPError as error:
                try:
                    if error.code == 429:
                        raise BeatweaveError(
                            "wan2gp_auth_rate_limited",
                            "WanGP login is rate limited. Wait before trying the password again.",
                        ) from error
                    if error.code in {401, 403}:
                        raise BeatweaveError(
                            "wan2gp_auth_failed",
                            "WanGP rejected the password or login origin. Check Settings > Video.",
                        ) from error
                    raise BeatweaveError(
                        "wan2gp_auth_failed", "WanGP's web login could not be completed."
                    ) from error
                finally:
                    error.close()
            except (URLError, OSError, TimeoutError, UnicodeError) as error:
                raise BeatweaveError(
                    "wan2gp_unavailable", "WanGP's web login is unreachable."
                ) from error
        return {cookie.name: cookie.value for cookie in self.jar if cookie.name == "wangp_session"}

    def get_json(self, path: str) -> dict[str, Any]:
        self.authenticate()
        try:
            with self.opener.open(
                Request(f"{self.config.base_url}{path}", headers={"Accept": "application/json"}),
                timeout=self.config.request_timeout_seconds,
            ) as response:
                return json.loads(response.read())
        except HTTPError as error:
            try:
                if error.code in {401, 403}:
                    raise BeatweaveError(
                        "wan2gp_auth_failed",
                        "WanGP authentication expired or was rejected. Check the web password.",
                    ) from error
                raise BeatweaveError("wan2gp_unavailable", "WanGP's API is unreachable.") from error
            finally:
                error.close()
        except (URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
            raise BeatweaveError("wan2gp_unavailable", "WanGP's API is unreachable.") from error
