"""Logs structurés JSON (CLAUDE.md §3 et §13 : aucun `print()`)."""

from __future__ import annotations

import logging
import sys

import structlog


class SansTrace(logging.Filter):
    """Retire la trace d'exécution des enregistrements de la bibliothèque standard.

    Starlette relance toute exception non rattrapée après avoir appelé son
    gestionnaire (`starlette/middleware/errors.py`, commentaire « We always
    continue to raise the exception ») : uvicorn la journalise alors avec
    `exc_info` sur le logger `uvicorn.error`, et le formateur par défaut écrit
    la trace complète sur la sortie standard. Or une erreur SQLAlchemy embarque
    couramment ses paramètres liés — donc l'adresse et le numéro de
    l'utilisateur (CLAUDE.md §14.4). La réponse HTTP et la ligne structlog
    (`src/api/app.py`) sont propres ; ce filtre ferme le dernier chemin par
    lequel la donnée sortait encore, sur stdout, hors du contrôle de structlog.

    Le type de l'exception reste journalisé par le gestionnaire global de
    `src/api/app.py` : on ne perd pas la trace de l'incident, seulement son
    contenu.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.exc_info = None
        record.exc_text = None
        return True


def setup_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    """Configure structlog et la stdlib. Appelé une fois par entrypoint."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    # `uvicorn.error` est le logger sur lequel Starlette/uvicorn journalisent
    # avec `exc_info` toute exception non rattrapée qui traverse l'ASGI (cf.
    # `SansTrace`) : c'est exactement le chemin de fuite vérifié (défaut du
    # 2026-09-11). Portée volontairement limitée à ce logger, pour deux
    # raisons vérifiées, pas supposées :
    #
    # - `sqlalchemy` : `echo=False` partout (`src/db/session.py`) et rien
    #   dans ce dépôt ne configure son logger — pas de risque constaté.
    # - `asyncio` journalise, lui aussi, avec `exc_info` toute exception
    #   d'une tâche jamais récupérée (« Task exception was never retrieved »)
    #   — et `src/ingest/fraicheur.py` en crée une (fire-and-forget, `raise`
    #   après le `log.error`) qui pourrait un jour porter des paramètres liés.
    #   Mais ce même mécanisme est aussi celui d'une panne de démarrage
    #   (vérifié : un hook `startup` qui échoue journalise sa trace via
    #   `asyncio`, pas `uvicorn.error`) — y appliquer `SansTrace` couperait ce
    #   diagnostic-là dans les quatre process. Non traité ici : ni la racine,
    #   ni `asyncio` seul, ne referment cette fuite sans ce coût ; voir le
    #   rapport de la correction pour le détail et la piste de remédiation.
    # - `aiogram.event` journalise lui aussi les exceptions de traitement
    #   d'un update avec `exc_info` (`_process_update`), mais **le message
    #   embarque déjà `str(exc)` en clair** (`"...%s: %s", type, e`) — un
    #   filtre sur `exc_info` ne fermerait pas cette fuite-là, seulement sa
    #   trace. Un no-op trompeur : pas ajouté ici, signalé dans le rapport.
    logging.getLogger("uvicorn.error").addFilter(SansTrace())

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Logger nommé, à utiliser partout à la place de `print`."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
