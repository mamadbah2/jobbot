"""Entrypoint du process `bot` : aiogram + serveur HTTP (healthcheck, webhook §10)."""

from __future__ import annotations

import asyncio
import contextlib

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramUnauthorizedError

from src.bot.handlers import build_router
from src.config import Settings, get_settings
from src.db.session import dispose_engine
from src.health import create_app
from src.logging_setup import get_logger, setup_logging

log = get_logger(__name__)


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_router())
    return dp


async def _run_http(settings: Settings) -> None:
    """Sert /health dans le même process (CLAUDE.md §4)."""
    config = uvicorn.Config(
        create_app(),
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,  # structlog gère déjà les logs
        access_log=False,
    )
    await uvicorn.Server(config).serve()


async def _run_telegram(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    """Long-polling.

    Le timeout est volontairement court : le FAI local coupe `api.telegram.org`
    par intermittence et aiogram doit pouvoir se reconnecter vite (§15).
    En production, on passera au webhook.
    """
    if settings.telegram_mode == "webhook":
        # Implémenté en Phase 5, en même temps que le webhook de paiement.
        raise NotImplementedError(
            "Le mode webhook sera implémenté en Phase 5. Utilisez TELEGRAM_MODE=polling."
        )

    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, polling_timeout=settings.telegram_long_poll_timeout)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.is_prod)

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = _build_dispatcher()

    log.info(
        "demarrage_bot",
        environment=settings.environment,
        telegram_mode=settings.telegram_mode,
        http_port=settings.http_port,
    )

    http_task = asyncio.create_task(_run_http(settings), name="http")
    telegram_task = asyncio.create_task(_run_telegram(bot, dp, settings), name="telegram")

    try:
        done, pending = await asyncio.wait(
            {http_task, telegram_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in done:
            # Propage l'erreur qui a fait tomber le process, sans plantage silencieux (§7).
            task.result()
    except TelegramUnauthorizedError:
        # Erreur de configuration, pas de réseau : on veut un message lisible
        # dans les logs plutôt qu'une pile d'exceptions.
        log.error(
            "token_telegram_invalide",
            message=(
                "Telegram refuse le token. Renseignez un TELEGRAM_BOT_TOKEN "
                "obtenu auprès de @BotFather dans le fichier .env."
            ),
        )
        raise
    finally:
        await bot.session.close()
        await dispose_engine()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
