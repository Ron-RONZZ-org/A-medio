"""CLI for medio command (filmeto, foto, audio)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.table import Table

from A import error, info, tr, tr_multi
from A_medio.config import (
    get_cookies_from_browser,
    get_setting,
    set_cookies_from_browser,
    set_setting,
)
from A_medio.services.youtube import get_youtube_service
from A_medio.services.youtube._cookie_helpers import _detect_available_browsers

app = typer.Typer(
    name="medio",
    help=tr_multi(
        "Medio — video, photo, audio management.",
        "Medio — video, photo, audio management.",
        "Medio — gestion de médias (vidéo, photo, audio).",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

filmeto = typer.Typer(
    name="filmeto",
    help=tr_multi(
        "Filmeto — video management (YouTube, local).",
        "Filmeto — video management (YouTube, local).",
        "Filmeto — gestion vidéo (YouTube, local).",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(filmeto, name="filmeto")

foto = typer.Typer(
    name="foto",
    help=tr_multi(
        "Foto — photo management.",
        "Foto — photo management.",
        "Foto — gestion de photos.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(foto, name="foto")

audio = typer.Typer(
    name="audio",
    help=tr_multi(
        "Audio — audio/podcast management.",
        "Audio — audio/podcast management.",
        "Audio — gestion audio/podcast.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(audio, name="audio")

config = typer.Typer(
    name="config",
    help=tr_multi(
        "Agordi — view or change plugin settings.",
        "Config — view or change plugin settings.",
        "Config — voir ou modifier les réglages.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(config, name="config")


@config.command("get")
def config_get(key: str) -> None:
    """Show a plugin setting.

    Examples:
        medio config get download_dir
        medio config get search_strategy
    """
    value = get_setting(key)
    if value is None:
        info(tr_multi(
            f"Agordo '{key}' ne estas difinita.",
            f"Setting '{key}' is not set.",
            f"Le réglage '{key}' n'est pas défini.",
        ))
    else:
        info(f"{key} = {value}")


@config.command("set")
def config_set(key: str, value: str) -> None:
    """Set a plugin setting.

    Examples:
        medio config set download_dir /path/to/downloads
        medio config set search_strategy '{"mode": "deep"}'
    """
    import json

    # Try parsing as JSON for non-string values
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value

    set_setting(key, parsed)
    info(tr_multi(
        f"Agordo '{key}' agordita.",
        f"Setting '{key}' saved.",
        f"Réglage '{key}' enregistré.",
    ))


# ── Helper functions ───────────────────────────────────────────────────────────


def _auto_setup_cookies() -> tuple[str | None, str | None]:
    """Auto-detect browser cookies and prompt user on first call.

    Probes all known Firefox-style browsers for profiles that have
    ``cookies.sqlite``.  If any are found, shows the user a confirmation
    prompt and, on acceptance, saves the preference to config.

    Returns:
        ``(browser_name, profile_path)`` if the user accepted,
        ``(None, None)`` if no browsers found, user declined, or
        running non-interactively.
    """
    # Only prompt in interactive terminals
    if not sys.stdin.isatty():
        return (None, None)

    detected = _detect_available_browsers()
    if not detected:
        return (None, None)

    # Pick the first detected browser+profile as the default suggestion
    browser = next(iter(detected))
    profiles = detected[browser]
    profile = profiles[0] if profiles else None

    if profile:
        prompt_msg = tr_multi(
            f"Detektis {browser} kuketojn de {profile}. Ĉu uzi por YouTube?",
            f"Detected {browser} cookies from {profile}. Use for YouTube?",
            f"Cookies {browser} détectés depuis {profile}. Utiliser pour YouTube ?",
        )
    else:
        prompt_msg = tr_multi(
            f"Detektis {browser} retumilon. Ĉu uzi kuketojn por YouTube?",
            f"Detected {browser} browser. Use cookies for YouTube?",
            f"Navigateur {browser} détecté. Utiliser les cookies pour YouTube ?",
        )

    from A.utils.interactive import confirm_action

    if not confirm_action(prompt_msg, default=True):
        info(tr_multi(
            "Neniu retumilo agordita. Uzu --kuketoj au --kuketoj-de-retumilo permane.",
            "No browser configured. Use --kuketoj or --kuketoj-de-retumilo manually.",
            "Aucun navigateur configuré. Utilisez --kuketoj ou --kuketoj-de-retumilo manuellement.",
        ))
        return (None, None)

    # Save to persistent config for future calls
    set_cookies_from_browser(browser, profile)
    info(tr_multi(
        f"Konservis {browser} kiel defauxltan retumilon por kuketoj.",
        f"Saved {browser} as default cookie browser.",
        f"{browser} enregistré comme navigateur de cookies par défaut.",
    ))
    return (browser, profile)


_DEFAULT_OUTTMPL = "%(title).80s [%(id)s].%(ext)s"


def _resolve_output_template(output_path_str: str) -> tuple[Path, str]:
    """Resolve a user-supplied output path to ``(directory, outtmpl)``.

    Rules (in priority order):

    1. **Existing directory** → use as-is with default template.
    2. **Ends with ``/``** → create the directory (parents), default template.
    3. **Non-existent, no suffix, >1 part** → treat as directory, default
       template.
    4. **Everything else** → extract parent as directory, use stem as template.

    This matches the legacy
    ``autish.commands.filmeto._resolve_output_template`` behaviour.

    Args:
        output_path_str: Raw string from the ``--output``/``-o`` CLI option.

    Returns:
        ``(resolved_output_dir, outtmpl_string)``
    """
    output_path = Path(output_path_str)
    expanded = output_path.expanduser().resolve()

    # Rule 1: existing directory
    if expanded.exists() and expanded.is_dir():
        return expanded, _DEFAULT_OUTTMPL

    # Rule 2: trailing slash → create directory
    if output_path_str.endswith("/"):
        expanded.mkdir(parents=True, exist_ok=True)
        return expanded, _DEFAULT_OUTTMPL

    # Rule 3: non-existent, no suffix, multiple path parts → directory
    if (
        not expanded.exists()
        and output_path.suffix == ""
        and output_path.name != ""
        and len(output_path.parts) > 1
    ):
        return expanded, _DEFAULT_OUTTMPL

    # Rule 4: treat as file template
    parent = expanded.parent
    parent.mkdir(parents=True, exist_ok=True)
    base = expanded.stem if expanded.suffix else expanded.name
    return parent, f"{base}.%(ext)s"


def _download_with_confirmation(
    url: str,
    youtube: Any,
    opts: dict[str, Any],
) -> list[Path]:
    """Estimate and confirm download before proceeding.

    Runs a dry-run estimation, shows a Rich table preview with title,
    duration, and file size, then prompts the user before downloading.

    Args:
        url: YouTube URL to download.
        youtube: The ``YouTubeService`` instance.
        opts: Download options forwarded to both :meth:`estimate` and
            :meth:`download`.

    Returns:
        List of downloaded file paths (empty if cancelled or failed).
    """
    # Only prompt in interactive terminals
    if not sys.stdin.isatty():
        return youtube.download(url, **opts)

    estimate = youtube.estimate(url, **opts)
    if estimate is None or not estimate.items:
        error(tr_multi(
            "Ne povis taksi elsxuton. Nuligita.",
            "Could not estimate download. Cancelled.",
            "Impossible d'estimer le téléchargement. Annulé.",
        ))
        return []

    # Build preview table
    table = Table(title=tr_multi(
        "Elsxuta resumo",
        "Download summary",
        "Résumé du téléchargement",
    ))
    table.add_column(tr_multi("Titolo", "Title", "Titre"))
    table.add_column(tr_multi("Daŭro", "Duration", "Durée"), width=10)
    table.add_column(tr_multi("Grandeco", "Size", "Taille"), width=12)
    for item in estimate.items:
        title = item.get("title", "-")
        duration_sec = int(item.get("duration", 0))
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_str = f"{minutes}:{seconds:02d}" if duration_sec > 0 else "-"
        file_bytes = int(item.get("filesize", 0))
        if file_bytes > 0:
            size_str = (
                f"{file_bytes / 1024 / 1024:.1f} MB"
                if file_bytes > 1024 * 1024
                else f"{file_bytes / 1024:.1f} KB"
            )
        else:
            size_str = "-"
        table.add_row(title, duration_str, size_str)

    info(tr_multi(
        f"Taksita: {estimate.count} dosiero(j), ~{estimate.total_size_str}",
        f"Estimated: {estimate.count} file(s), ~{estimate.total_size_str}",
        f"Estimé : {estimate.count} fichier(s), ~{estimate.total_size_str}",
    ))

    from A.utils.interactive import confirm_action

    if not confirm_action(
        tr_multi(
            "Ĉu daŭrigi elsxuton?",
            "Continue with download?",
            "Continuer le téléchargement ?",
        ),
        default=True,
    ):
        info(tr_multi(
            "Nuligita.",
            "Cancelled.",
            "Annulé.",
        ))
        return []

    return youtube.download(url, **opts)


# filmeto subcommands
# ──────────────────────────────────────────────────────────────────────────────


@filmeto.command("kuketoj-helpo")
def filmeto_kuketoj_helpo() -> None:
    """Show detailed instructions for YouTube cookie setup.

    Explains how to find browser profiles, use --kuketoj for cookie files,
    and use --kuketoj-de-retumilo for browser-based cookie extraction.
    """
    from A_medio.services.youtube import _cookie_help_text
    info(_cookie_help_text())


@filmeto.command("serci")
def filmeto_serci(
    query: str,
    limit: int = 10,
    filter_field: Optional[str] = typer.Option(None, "--filter", "-f", help=tr_multi("Filtrila kampo (titolo, priskribo, aŭtoro)", "Filter field (title, description, author)", "Champ de filtrage (titre, description, auteur)")),
    regex: Optional[str] = typer.Option(None, "--regex", "-r", help=tr_multi("Regex ŝablono por kongruigi", "Regex pattern to match", "Motif Regex à faire correspondre")),
    local_only: bool = typer.Option(False, "--local", "-l", help=tr_multi("Serĉi nur lokan kaŝmemoron", "Search local cache only", "Rechercher uniquement le cache local")),
    aldona: bool = typer.Option(False, "--aldona", "-a", help=tr_multi("Montri krominformojn (vidadoj,abonantoj).", "Show extra info (views, subscribers).", "Afficher les infos supplémentaires (vues, abonnés).")),
    playlistoj: bool = typer.Option(False, "--playlistoj", "-P", help=tr_multi("Serĉi ludlistojn anstataŭ videojn.", "Search playlists instead of videos.", "Rechercher des playlists au lieu de vidéos.")),
    kuketoj: Optional[str] = typer.Option(None, "--kuketoj", help=tr_multi("Vojo al cookies.txt por YouTube aŭtentigo.", "Path to cookies.txt for YouTube authentication.", "Chemin vers cookies.txt pour l'authentification YouTube.")),
    kuketoj_de_retumilo: Optional[str] = typer.Option(
        None, "--kuketoj-de-retumilo",
        help=(
            "Browser to extract cookies from. "
            "Valid values: firefox, floorp, librewolf, waterfox, zen (Firefox-based), "
            "chrome, brave, vivaldi, chromium (Chromium-based). "
            "Append :profile_path for a specific profile. "
            "Example: --kuketoj-de-retumilo floorp"
        ),
    ),
) -> None:
    """Search videos on YouTube.

    If search fails (e.g. YouTube blocks unauthenticated requests), try
    --kuketoj or --kuketoj-de-retumilo to provide authentication cookies.
    Use --aldona for extra details or --playlistoj to find playlists.

    Examples:
        medio filmeto serci "python tutorial"
        medio filmeto serci "music" --filter author --regex "official"
        medio filmeto serci "news" --local
        medio filmeto serci "news" --aldona
        medio filmeto serci "python" --playlistoj
        medio filmeto serci "tutorial" --kuketoj /tmp/cookies.txt
        medio filmeto serci "music" --kuketoj-de-retumilo floorp
    """
    youtube = get_youtube_service()

    if not youtube.is_available() and not local_only:
        if not youtube.ensure_installed():
            return

    if local_only:
        results = youtube.search_local(query, limit=limit)
    else:
        opts: dict[str, Any] = {"limit": limit}
        if filter_field and regex:
            opts["filter"] = filter_field
            opts["regex"] = regex
        elif regex:
            opts["regex"] = regex
        if kuketoj:
            opts["cookies"] = kuketoj
        if kuketoj_de_retumilo:
            opts["cookies_from_browser"] = kuketoj_de_retumilo
        # Auto-detect cookies on first call (no explicit flags, no config-saved browser)
        if not kuketoj and not kuketoj_de_retumilo and not get_cookies_from_browser():
            browser, profile = _auto_setup_cookies()
            if browser:
                if profile:
                    opts["cookies_from_browser"] = f"{browser}:{profile}"
                else:
                    opts["cookies_from_browser"] = browser
        # Playlist search: append " playlist" to seed
        search_query = f"{query} playlist" if playlistoj else query
        results = youtube.search(search_query, **opts)

    if not results:
        info(tr_multi(
            "Neniuj rezultoj trovitaj. Provu --kuketoj aŭ --kuketoj-de-retumilo.",
            "No results found. Try --kuketoj or --kuketoj-de-retumilo.",
            "Aucun résultat trouvé. Essayez --kuketoj ou --kuketoj-de-retumilo.",
        ))
        return

    # Display results
    for i, video in enumerate(results, 1):
        title = video.get("title", "")
        author = video.get("author", "")
        url = video.get("url", "")
        info(f"{i}. {title} [dim]({author})[/dim]")
        info(f"   {url}")
        if aldona:
            views = video.get("view_count", "")
            subs = video.get("channel_follower_count", "")
            duration = video.get("duration", 0)
            parts: list[str] = []
            if views:
                parts.append(f"Views: {views}")
            if subs:
                parts.append(f"Subs: {subs}")
            if duration:
                minutes = duration // 60
                seconds = duration % 60
                parts.append(f"Dur: {minutes}:{seconds:02d}")
            if parts:
                info(f"   [dim]{' | '.join(parts)}[/dim]")


@filmeto.command("eljuti")
def filmeto_eljuti(
    url: Optional[str] = typer.Argument(None, help=tr_multi("YouTube URL por elŝuti. Ne necesa kun --csv-dosiero.", "YouTube URL to download. Not needed when using --csv-dosiero.", "URL YouTube à télécharger. Pas nécessaire avec --csv-dosiero.")),
    output_path: Optional[str] = typer.Option(None, "--output", "-o", help=tr_multi("Elŝuta vojo (dosierujo aŭ dosiero). Ekz: '/videoj/', 'video.mp4', '/vojo/al/dosierujo/'.", "Download path (directory or file). Ex: '/videos/', 'video.mp4', '/path/to/dir/'.", "Chemin de téléchargement (dossier ou fichier). Ex: '/videos/', 'video.mp4', '/chemin/vers/dossier/'.")),
    resolution: Optional[int] = typer.Option(None, "--difino", "-d", help=tr_multi("Maksimuma video distingivo (ekz. 720, 1080).", "Max video resolution (e.g. 720, 1080).", "Résolution vidéo max (ex: 720, 1080).")),
    audio_only: bool = typer.Option(False, "--audio", "-A", help=tr_multi("Eltiri nur audio.", "Extract audio only.", "Extraire uniquement l'audio.")),
    video_only: bool = typer.Option(False, "--filmeto", "-F", help=tr_multi("Video streamo nur (sen audio).", "Video stream only (no audio).", "Flux vidéo uniquement (sans audio).")),
    audio_bitrate: Optional[int] = typer.Option(None, "--sonkvalito", "-s", help=tr_multi("Maksimuma sonkvalito en kbps.", "Max audio bitrate in kbps.", "Débit audio max en kbps.")),
    subtitles: Optional[str] = typer.Option(
        None, "--subtitoloj", "--sub",
        help=tr_multi("Subtitoloj: 'auto', 'all', aŭ punktokomo-separitaj lingvokodoj (ekz. 'eo,en,fr').", "Subtitles: 'auto', 'all', or comma-separated language codes (e.g. 'eo,en,fr').", "Sous-titres: 'auto', 'all', ou codes de langue séparés par virgule (ex: 'eo,en,fr')."),
    ),
    taksi: bool = typer.Option(False, "--taksi", "-t", help=tr_multi("Taksi grandecon nur, ne elŝuti.", "Estimate size only, do not download.", "Estimer la taille uniquement, ne pas télécharger.")),
    limo: Optional[int] = typer.Option(
        None, "--limo", "-lo",
        help=tr_multi("Maksimumaj eroj elŝutendaj el ludlisto.", "Max items to download from a playlist.", "Éléments max à télécharger d'une playlist."),
    ),
    kuketoj: Optional[str] = typer.Option(None, "--kuketoj", help=tr_multi("Vojo al cookies.txt por YouTube aŭtentigo.", "Path to cookies.txt for YouTube authentication.", "Chemin vers cookies.txt pour l'authentification YouTube.")),
    kuketoj_de_retumilo: Optional[str] = typer.Option(
        None, "--kuketoj-de-retumilo",
        help=(
            "Browser to extract cookies from. "
            "Valid values: firefox, floorp, librewolf, waterfox, zen (Firefox-based), "
            "chrome, brave, vivaldi, chromium (Chromium-based). "
            "Append :profile_path for a specific profile."
        ),
    ),
    csv_dosiero: Optional[Path] = typer.Option(
        None, "--csv-dosiero", "--csv",
        help=tr_multi("CSV dosiero por amasa elŝuto. Kolumnoj: celoj,difino,sonkvalito,audio,filmeto,vojo,subtitoloj,kuketoj,kuketoj_de_retumilo.", "CSV file for batch download. Columns: celoj,difino,sonkvalito,audio,filmeto,vojo,subtitoloj,kuketoj,kuketoj_de_retumilo.", "Fichier CSV pour téléchargement par lots. Colonnes: celoj,difino,sonkvalito,audio,filmeto,vojo,subtitoloj,kuketoj,kuketoj_de_retumilo."),
        exists=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """Download a video/audio from YouTube.

    Provide a single URL as argument, or use --csv-dosiero for batch download.

    Use --taksi to preview estimated size before downloading.
    Use --limo to limit how many items are fetched from a playlist.

    If downloads fail due to YouTube blocking, try --kuketoj or --kuketoj-de-retumilo.

    Examples:
        medio filmeto eljuti https://www.youtube.com/watch?v=...
        medio filmeto eljuti https://youtu.be/... --output /path/to/dir
        medio filmeto eljuti https://youtu.be/... --audio
        medio filmeto eljuti https://youtu.be/... --difino 1080 --subtitoloj eo,en
        medio filmeto eljuti https://youtu.be/... --taksi
        medio filmeto eljuti https://youtu.be/... --limo 5
        medio filmeto eljuti https://youtu.be/... --kuketoj /tmp/cookies.txt
        medio filmeto eljuti --csv-dosiero elsutoj.csv
    """
    from A_medio.services.youtube import parse_csv_rows

    youtube = get_youtube_service()

    if not youtube.is_available():
        if not youtube.ensure_installed():
            return

    # ── CSV batch mode ────────────────────────────────────────────────────
    if csv_dosiero is not None:
        # Build initial state from CLI flags
        initial: dict[str, Any] = {}
        if output_path is not None:
            resolved_dir, _ = _resolve_output_template(output_path)
            initial["output_dir"] = str(resolved_dir)
        if resolution is not None:
            initial["resolution"] = resolution
        if audio_only:
            initial["audio_only"] = True
        if video_only:
            initial["video_only"] = True
        if audio_bitrate is not None:
            initial["audio_bitrate"] = audio_bitrate
        if subtitles is not None:
            initial["subtitles"] = subtitles
        if kuketoj is not None:
            initial["cookies"] = kuketoj
        if kuketoj_de_retumilo is not None:
            initial["cookies_from_browser"] = kuketoj_de_retumilo
        if limo is not None:
            initial["playlist_end"] = limo

        try:
            specs = parse_csv_rows(csv_dosiero, initial_state=initial)
        except (FileNotFoundError, ValueError) as exc:
            error(str(exc))
            return

        if not specs:
            info(tr_multi(
                "Neniuj specifoj trovita en CSV.",
                "No specs found in CSV.",
                "Aucune spécification trouvée dans le CSV.",
            ))
            return

        # Resolve output paths in each CSV spec (directory or file)
        for spec in specs:
            raw_vojo = spec.get("output_dir")
            if raw_vojo and isinstance(raw_vojo, str):
                resolved_dir, outtmpl = _resolve_output_template(raw_vojo)
                spec["output_dir"] = str(resolved_dir)
                spec["outtmpl"] = outtmpl

        results = youtube.batch_download(specs)

        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        info(tr_multi(
            f"Pretigis {len(results)} celo(j)n: {success_count} sukcese, {fail_count} malsukcese.",
            f"Processed {len(results)} target(s): {success_count} succeeded, {fail_count} failed.",
            f"Traité {len(results)} cible(s) : {success_count} réussi, {fail_count} échoué.",
        ))

        for r in results:
            if r.success:
                info(f"  ✓ {r.url}")
                for f in r.files:
                    info(f"    {f}")
            else:
                error(f"  ✗ {r.url}: {r.error}")
        return

    # ── Single URL mode ───────────────────────────────────────────────────
    if not url:
        error(tr_multi(
            "Mankas URL. Uzu: medio filmeto eljuti <URL> aŭ --csv-dosiero <dosiero>.",
            "Missing URL. Use: medio filmeto eljuti <URL> or --csv-dosiero <file>.",
            "URL manquante. Utilisez : medio filmeto eljuti <URL> ou --csv-dosiero <fichier>.",
        ))
        return

    # ── Cookie auto-setup (same guard as serci) ──────────────────────────
    if not kuketoj and not kuketoj_de_retumilo and not get_cookies_from_browser():
        browser, profile = _auto_setup_cookies()
        if browser:
            kuketoj_de_retumilo = (
                f"{browser}:{profile}" if profile else browser
            )

    # ── Resolve output path ────────────────────────────────────────────────
    if output_path is not None:
        resolved_dir, outtmpl = _resolve_output_template(output_path)
        download_opts: dict[str, Any] = {
            "output_dir": str(resolved_dir),
            "outtmpl": outtmpl,
        }
    else:
        download_opts: dict[str, Any] = {
            "output_dir": youtube.get_download_dir(),
        }
    if resolution is not None:
        download_opts["resolution"] = resolution
    if audio_only:
        download_opts["audio_only"] = True
    if video_only:
        download_opts["video_only"] = True
    if audio_bitrate is not None:
        download_opts["audio_bitrate"] = audio_bitrate
    if subtitles is not None:
        download_opts["subtitles"] = subtitles
    if kuketoj is not None:
        download_opts["cookies"] = kuketoj
    if kuketoj_de_retumilo is not None:
        download_opts["cookies_from_browser"] = kuketoj_de_retumilo
    if limo is not None:
        download_opts["playlist_end"] = limo

    # ── Estimate mode ──────────────────────────────────────────────────────
    if taksi:
        estimate = youtube.estimate(url, **download_opts)
        if estimate is None:
            return
        info(tr_multi(
            f"Taksita: {estimate.count} dosiero(j), ~{estimate.total_size_str}",
            f"Estimated: {estimate.count} file(s), ~{estimate.total_size_str}",
            f"Estimé : {estimate.count} fichier(s), ~{estimate.total_size_str}",
        ))
        for item in estimate.items:
            title = item.get("title", "")
            fs = int(item.get("filesize", 0))
            if fs > 0:
                size_str = f"{fs / 1024 / 1024:.1f} MB" if fs > 1024 * 1024 else f"{fs / 1024:.1f} KB"
            else:
                size_str = "--"
            info(f"  {title} [dim]({size_str})[/dim]")
        return

    files = _download_with_confirmation(url, youtube, download_opts)

    if files:
        info(tr_multi(
            f"Elŝutis {len(files)} dosiero(j)n.",
            f"Downloaded {len(files)} file(s).",
            f"Téléchargé {len(files)} fichier(s).",
        ))
        for f in files:
            info(f"  {f}")


# ──────────────────────────────────────────────────────────────────────────────
# foto subcommands
# ──────────────────────────────────────────────────────────────────────────────


@foto.command("ls")
def foto_ls() -> None:
    """List photos."""
    info("[dim]TODO: implement foto ls[/dim]")


@foto.command("serci")
def foto_serci(query: str) -> None:
    """Search photos."""
    info(f"[dim]TODO: implement foto serci {query}[/dim]")


# ──────────────────────────────────────────────────────────────────────────────
# audio subcommands
# ──────────────────────────────────────────────────────────────────────────────


@audio.command("ls")
def audio_ls() -> None:
    """List audio/podcasts."""
    info("[dim]TODO: implement audio ls[/dim]")


@audio.command("ludi")
def audio_ludi(title: str) -> None:
    """Play audio."""
    info(f"[dim]TODO: implement audio ludi {title}[/dim]")


__all__ = ["app", "filmeto", "foto", "audio"]