"""CLI for medio command (filmeto, foto, audio)."""

from __future__ import annotations

import typer

from A import info, tr

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
def filmeto_serci(query: str) -> None:
    """Search videos."""
    info(f"[dim]TODO: implement filmeto serci {query}[/dim]")


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