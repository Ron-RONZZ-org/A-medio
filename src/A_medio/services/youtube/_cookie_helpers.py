"""Cookie and browser authentication helpers for yt-dlp."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Map browser forks to their base browser for yt-dlp's cookiesfrombrowser.
_BROWSER_FORK_MAP: dict[str, str] = {
    "floorp": "firefox",
    "librewolf": "firefox",
    "waterfox": "firefox",
    "zen": "firefox",
    "brave": "chrome",
    "vivaldi": "chrome",
    "chromium": "chrome",
}


def _parse_cookies_from_browser(raw: str) -> tuple[str, ...]:
    """Parse a ``browser:profile`` string into a yt-dlp ``cookiesfrombrowser`` tuple.

    Args:
        raw: ``"browser"`` or ``"browser:/path/to/profile"``.

    Returns:
        A tuple compatible with yt-dlp's ``cookiesfrombrowser`` option.
    """
    value = raw.strip()
    if ":" in value:
        browser_raw, profile = value.split(":", 1)
        browser = _BROWSER_FORK_MAP.get(browser_raw.strip().lower(), browser_raw.strip().lower())
        profile = profile.strip()
        if profile:
            return (browser, profile, None, None)
        return (browser,)
    browser = _BROWSER_FORK_MAP.get(value.lower(), value.lower())
    return (browser,)


def _discover_firefox_profiles(browser_hint: str) -> list[str]:
    """Auto-discover Firefox-style browser profiles that have cookies.

    Args:
        browser_hint: Browser name (floorp, librewolf, firefox, etc.).

    Returns:
        List of absolute profile directory paths.
    """
    home = Path.home()
    hint = browser_hint.strip().lower()
    roots: list[Path] = []
    if hint == "floorp":
        roots.append(home / ".floorp")
    elif hint in {"librewolf"}:
        roots.append(home / ".librewolf")
    elif hint in {"waterfox"}:
        roots.append(home / ".waterfox")
    elif hint in {"zen"}:
        roots.append(home / ".zen")
    else:
        roots.append(home / ".mozilla" / "firefox")

    profiles: list[str] = []
    for root in roots:
        profiles_ini = root / "profiles.ini"
        if profiles_ini.exists():
            try:
                current_section = ""
                values: dict[str, dict[str, str]] = {}
                for raw_line in profiles_ini.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith(";"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line[1:-1].strip()
                        values.setdefault(current_section, {})
                        continue
                    if "=" not in line or not current_section:
                        continue
                    k, v = line.split("=", 1)
                    values.setdefault(current_section, {})[k.strip()] = v.strip()
                for section, cfg in values.items():
                    if not section.lower().startswith("profile"):
                        continue
                    raw_path = cfg.get("Path", "").strip()
                    if not raw_path:
                        continue
                    is_relative = cfg.get("IsRelative", "1").strip() == "1"
                    candidate = (root / raw_path) if is_relative else Path(raw_path)
                    if (candidate / "cookies.sqlite").exists():
                        profiles.append(str(candidate))
            except OSError:
                pass
        if root.exists():
            for cookie_db in root.rglob("cookies.sqlite"):
                candidate = cookie_db.parent
                candidate_str = str(candidate)
                if candidate_str not in profiles:
                    profiles.append(candidate_str)

    unique: list[str] = []
    seen: set[str] = set()
    for p in profiles:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _detect_available_browsers() -> dict[str, list[str]]:
    """Probe all known Firefox-style browsers for profiles with cookies.

    Iterates over all browsers in ``_BROWSER_FORK_MAP`` that map to
    ``"firefox"``, plus ``"firefox"`` itself, and calls
    :func:`_discover_firefox_profiles` for each.

    Returns:
        Dict mapping browser name (e.g. ``"floorp"``, ``"firefox"``)
        to a list of absolute profile directory paths that contain
        a ``cookies.sqlite`` file.  Browsers with no profiles are
        omitted.
    """
    browsers: set[str] = set()
    for key, val in _BROWSER_FORK_MAP.items():
        if val == "firefox":
            browsers.add(key)
    browsers.add("firefox")

    result: dict[str, list[str]] = {}
    # Process in predictable order so tests can be deterministic
    for browser in sorted(browsers):
        try:
            profiles = _discover_firefox_profiles(browser)
        except OSError:
            profiles = []
        if profiles:
            result[browser] = profiles
    return result


def _cookie_browser_candidates(
    raw: str | None,
    *,
    config_browser: str | None = None,
    config_profile: str | None = None,
) -> list[tuple[str, ...] | None]:
    """Build a list of ``cookiesfrombrowser`` candidates to try.

    Args:
        raw: The ``--kuketoj-de-retumilo`` value, or ``None``.
        config_browser: Fallback browser name from persistent config.
            Used when *raw* is ``None``.
        config_profile: Optional profile path from persistent config.

    Returns:
        List of candidate tuples (or ``None`` for no cookies).
    """
    if not raw:
        if config_browser:
            # Use saved config preference instead of falling back to None
            base = (config_browser,)
            if config_profile:
                base = (config_browser, config_profile, None, None)
            candidates: list[tuple[str, ...] | None] = [base]
            mapped = _BROWSER_FORK_MAP.get(config_browser.lower(), config_browser.lower())
            if mapped == "firefox" and not config_profile:
                for profile in _discover_firefox_profiles(config_browser):
                    spec = (mapped, profile, None, None)
                    if spec not in candidates:
                        candidates.append(spec)
            if None not in candidates:
                candidates.append(None)
            return candidates
        return [None]
    value = raw.strip()
    if not value:
        return [None]

    base = _parse_cookies_from_browser(value)
    candidates: list[tuple[str, ...] | None] = [base]

    if ":" in value:
        browser_raw = value.split(":", 1)[0].strip().lower()
        mapped = _BROWSER_FORK_MAP.get(browser_raw, browser_raw)
        if mapped == "firefox":
            for profile in _discover_firefox_profiles(browser_raw):
                spec = (mapped, profile, None, None)
                if spec not in candidates:
                    candidates.append(spec)
        if None not in candidates:
            candidates.append(None)
        return candidates

    browser_raw = value.lower()
    mapped = _BROWSER_FORK_MAP.get(browser_raw, browser_raw)
    if mapped == "firefox":
        for profile in _discover_firefox_profiles(browser_raw):
            spec = (mapped, profile, None, None)
            if spec not in candidates:
                candidates.append(spec)
    return candidates


def build_cookie_opts(
    cookies: str | None = None,
    cookies_from_browser: str | None = None,
) -> dict[str, Any]:
    """Build yt-dlp options for cookie authentication.

    Args:
        cookies: Path to a Netscape-format cookies.txt file.
        cookies_from_browser: Browser name or ``"browser:profile"`` string.

    Returns:
        Dict with ``cookiefile`` and/or ``cookiesfrombrowser`` keys.
    """
    opts: dict[str, Any] = {}
    if cookies:
        opts["cookiefile"] = cookies
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = _parse_cookies_from_browser(cookies_from_browser)
    return opts


def _cookie_help_text() -> str:
    """Return detailed help text for cookie setup."""
    home = Path.home()
    return (
        "Kuketoj helpo:\n"
        "  1) Trovu vian retumilan profilon.\n"
        f"     Floorp (Linux): {home}/.floorp/<profilo>\n"
        f"     Firefox (Linux): {home}/.mozilla/firefox/<profilo>\n"
        "     Konsilo: legu profiles.ini por gxusta profilo-nomo.\n"
        "  2) Testu kun:\n"
        "     --kuketoj-de-retumilo floorp\n"
        "     au --kuketoj-de-retumilo floorp:/plena/vojo/al/profilo\n"
        "     ekz.: --kuketoj-de-retumilo floorp:/home/vi/.floorp/abc.default-default\n"
        "     (la profilo devas enhavi cookies.sqlite)\n"
        "     Noto: filmeto automate provas plurajn profilojn por firefox/floorp.\n"
        "  3) CLI-kuketoj-eksporto (preferata):\n"
        "     pip install --user yt-dlp\n"
        "     yt-dlp --cookies-from-browser floorp --cookies /tmp/youtube.cookies.txt"
        " --skip-download https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "     au kun specifa profilo:\n"
        "     yt-dlp --cookies-from-browser firefox:/home/vi/.floorp/abc.default-default"
        " --cookies /tmp/youtube.cookies.txt --skip-download https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "     poste uzu: filmeto serci <teksto> --kuketoj /tmp/youtube.cookies.txt\n"
        "  4) Rapida diagnozo (CLI):\n"
        "     ls ~/.floorp\n"
        "     find ~/.floorp -maxdepth 3 -name cookies.sqlite\n"
        "  5) JavaScript-runtime por YouTube (rekomendata):\n"
        "     sudo apt install -y nodejs\n"
        "     (au instalu deno: https://deno.com/)\n"
        "  6) Se la konto uzas apartajn ujojn (containers),\n"
        "     provu retumilan defaaultan ujon."
    )
