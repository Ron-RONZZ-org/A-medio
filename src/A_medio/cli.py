"""CLI for medio command (filmeto, foto, audio)."""

from __future__ import annotations

from typing import Any, Optional

import typer

from A import error, info, tr, tr_multi
from A_medio.config import get_setting, set_setting
from A_medio.services.youtube import get_youtube_service

app = typer.Typer(
    name="medio",
    help=tr_multi(
        "Medio — video, photo, audio management.",
        "Medio — video, photo, audio management.",
        "Medio — gestion de médias (vidéo, photo, audio).",
    ),
    no_args_is_help=False,
    invoke_without_command=True,
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


# filmeto subcommands
# ──────────────────────────────────────────────────────────────────────────────


@filmeto.command("serci")
def filmeto_serci(
    query: str,
    limit: int = 10,
    filter_field: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter field (title, description, author)"),
    regex: Optional[str] = typer.Option(None, "--regex", "-r", help="Regex pattern to match"),
    local_only: bool = typer.Option(False, "--local", "-l", help="Search local cache only"),
) -> None:
    """Search videos on YouTube.

    Examples:
        medio filmeto serci "python tutorial"
        medio filmeto serci "music" --filter author --regex "official"
        medio filmeto serci "news" --local
    """
    youtube = get_youtube_service()

    if not youtube.is_available() and not local_only:
        error(tr_multi(
            "yt-dlp ne estas instalita. Uzu --local por serĉi en la loka kaŝmemoro.",
            "yt-dlp is not installed. Use --local to search local cache.",
            "yt-dlp n'est pas installé. Utilisez --local pour chercher dans le cache local.",
        ))
        return

    if local_only:
        results = youtube.search_local(query, limit=limit)
    else:
        opts = {"limit": limit}
        if filter_field and regex:
            opts["filter"] = filter_field
            opts["regex"] = regex
        elif regex:
            opts["regex"] = regex
        results = youtube.search(query, **opts)

    if not results:
        info(tr_multi(
            "Neniuj rezultoj trovitaj.",
            "No results found.",
            "Aucun résultat trouvé.",
        ))
        return

    # Display results
    for i, video in enumerate(results, 1):
        title = video.get("title", "")
        author = video.get("author", "")
        url = video.get("url", "")
        info(f"{i}. {title} [dim]({author})[/dim]")
        info(f"   {url}")


@filmeto.command("ludi")
def filmeto_ludi(url: str) -> None:
    """Play a video."""
    info(f"[dim]TODO: implement filmeto ludi {url}[/dim]")


@filmeto.command("eljuti")
def filmeto_eljuti(
    url: str,
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="Download directory (default: from config)."),
    resolution: Optional[int] = typer.Option(None, "--difino", "-d", help="Max video resolution (e.g. 720, 1080)."),
    audio_only: bool = typer.Option(False, "--audio", "-A", help="Extract audio only."),
    video_only: bool = typer.Option(False, "--filmeto", "-F", help="Video stream only (no audio)."),
    audio_bitrate: Optional[int] = typer.Option(None, "--sonkvalito", "-s", help="Max audio bitrate in kbps."),
    subtitles: Optional[str] = typer.Option(
        None, "--subtitoloj", "--sub",
        help="Subtitles: 'auto', 'all', or comma-separated language codes (e.g. 'eo,en,fr').",
    ),
) -> None:
    """Download a video/audio from YouTube.

    Examples:
        medio filmeto eljuti https://www.youtube.com/watch?v=...
        medio filmeto eljuti https://youtu.be/... --output /path/to/dir
        medio filmeto eljuti https://youtu.be/... --audio
        medio filmeto eljuti https://youtu.be/... --difino 1080 --subtitoloj eo,en
    """
    youtube = get_youtube_service()

    if not youtube.is_available():
        error(tr_multi(
            "yt-dlp ne estas instalita. Instalu ĝin por elŝuti.",
            "yt-dlp is not installed. Install it to download.",
            "yt-dlp n'est pas installé. Installez-le pour télécharger.",
        ))
        return

    download_opts: dict[str, Any] = {
        "output_dir": output_dir or youtube.get_download_dir(),
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

    files = youtube.download(url, **download_opts)

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