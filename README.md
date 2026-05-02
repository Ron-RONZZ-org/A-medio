# A-medio

## Context

For architecture and API reference, see [A-workspace](./workspace/).

A-medio - media management (video, photo, audio)

## Install

```bash
pip install A-medio
```

Requires **A-core** (automatically installed as dependency).

## Usage

```bash
A medio filmeto serci <query>  # Search videos
A medio filmeto ludi <url>     # Play video
A medio filmeto eljuti <url>   # Download video
A medio foto ls             # List photos
A medio audio ls            # List audio/podcasts
```

## Commands

A-medio provides three subcommands:

| Command | Description |
|---------|-------------|
| filmeto | Video management (YouTube, local) |
| foto | Photo management |
| audio | Audio/podcast management |

## About

A-medio is a plugin for the [A](https://github.com/Ron-RONZZ-org/A-core/) framework.

**A-medio depends on A-core** for:
- Plugin discovery via entry points
- i18n (tr() for multilingual support)
- SQLite with WAL mode
- Shared utilities (error(), info(), run())

See the [A-core documentation](https://github.com/Ron-RONZZ-org/A-core/) for more on the framework.

## History

A-medio is based on [autish filmeto](https://github.com/Ron-RONZZ-org/autish/), generalized to handle multiple media types.

## License

AGPL-3.0-only