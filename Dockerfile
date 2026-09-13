# Image unique pour les 4 process (api, worker_ingest, worker_match, migrate).
# La commande normale est choisie par docker-compose, pas ici (CMD n'est qu'un
# défaut de secours, cf. ci-dessous).
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

# `api` est le défaut le plus utile pour un `docker run jobbot` nu (réflexe de
# débogage sur le VPS) : c'est le seul process qui répond sur un port, et le
# web est désormais le seul client (CLAUDE.md §4). Même commande que le
# service `api` de docker-compose.yml. Sans CMD explicite, l'image hériterait
# de celui de `python:3.12-slim`, un interpréteur interactif.
CMD ["python", "-m", "src.api.main"]
