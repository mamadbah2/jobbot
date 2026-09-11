"""Entrypoint du process `api` (CLAUDE.md §4)."""

from __future__ import annotations

import asyncio
import contextlib

import uvicorn

from src.api.app import create_app
from src.config import get_settings
from src.db.session import dispose_engine
from src.logging_setup import get_logger, setup_logging

log = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.is_prod)
    log.info(
        "demarrage_api",
        environment=settings.environment,
        http_port=settings.http_port,
        fournisseur_courriel=settings.fournisseur_courriel,
    )
    config = uvicorn.Config(
        create_app(),
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,  # structlog gère déjà les logs
        access_log=False,
    )
    try:
        await uvicorn.Server(config).serve()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
