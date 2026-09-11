# Image unique pour les 5 process (api, bot, worker_ingest, worker_match, migrate).
# La commande est choisie par docker-compose, pas ici.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# uv : installation des dépendances nettement plus rapide que pip.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# Couche de dépendances isolée du code : modifier une source ne réinstalle pas
# tout. Le paquet lui-même est installé en editable, donc un src/ vide suffit ici.
COPY pyproject.toml README.md ./
RUN mkdir -p src && touch src/__init__.py \
    && uv pip install --system --no-cache -e '.[dev]'

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY tests/ ./tests/
COPY src/ ./src/

RUN useradd --create-home --uid 10001 jobbot && chown -R jobbot:jobbot /app
USER jobbot

CMD ["python", "-m", "src.bot.main"]
