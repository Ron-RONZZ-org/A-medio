"""CLI for medio command (filmeto, foto, audio)."""

from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr
from A_medio.services.youtube import get_youtube_service

app = typer.Typer(
    name="medio",
    help=tr(
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
    help=tr(
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
    help=tr(
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
    help=tr(
        "Audio — audio/podcast management.",
        "Audio — audio/podcast management.",
        "Audio — gestion audio/podcast.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(audio, name="audio")


# ──────────────────────────────────────────────────────────────────────────────
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
        error(tr(
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
        info(tr(
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
def filmeto_eljuti(url: str) -> None:
    """Download a video."""
    info(f"[dim]TODO: implement filmeto eljuti {url}[/dim]")


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