"""Handlers aiogram, regroupés par écran."""

from aiogram import Router

from src.bot.handlers import compte, start


def build_router() -> Router:
    """Router racine : agrège les routers de chaque écran."""
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(compte.router)
    return root


__all__ = ["build_router"]
