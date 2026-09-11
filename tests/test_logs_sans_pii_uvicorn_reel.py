"""Couche protocole : un vrai process uvicorn ne doit rien tracer sur stdout (§2).

`tests/test_logs_sans_pii.py` prouve que le pipeline structlog et le
gestionnaire global de `src/api/app.py` sont propres, mais `TestClient`
n'exécute jamais la couche protocole d'uvicorn : Starlette relance toute
exception non rattrapée après avoir appelé son gestionnaire
(`starlette/middleware/errors.py`, commentaire « We always continue to raise
the exception »), et c'est uvicorn — pas `TestClient` — qui la reçoit et la
journalise avec `exc_info` sur le logger `uvicorn.error`. Sans le filtre
`SansTrace` (`src/logging_setup.py`), le formateur par défaut de la
bibliothèque standard écrit alors la trace complète sur stdout, avec tout ce
que porte le message de l'exception — typiquement les paramètres liés d'une
erreur SQLAlchemy (adresse, numéro, §14.4).

Ce test monte donc un VRAI serveur uvicorn dans un process séparé (pas
`TestClient`), avec une route qui lève une exception dont le message contient
une adresse et un numéro, capture la sortie du process, et vérifie qu'aucun
des deux n'y figure, ni le mot « Traceback ».

Lancer avec : RUN_INTEGRATION_TESTS=1 pytest -m integration
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

RACINE_DEPOT = Path(__file__).resolve().parents[1]

ADRESSE = "fatou@jobbot-preuve.sn"
TEL = "+221771234567"

_SCRIPT_SERVEUR = '''
import sys
sys.path.insert(0, {racine!r})

from src.logging_setup import setup_logging
setup_logging("INFO", json_output=True)

from src.api.app import create_app
import uvicorn

app = create_app()


@app.get("/fuite-test")
async def _lever_une_exception_avec_pii() -> None:
    raise RuntimeError(
        "SQL error [parameters: ({adresse!r}, {tel!r})]"
    )


uvicorn.run(app, host={host!r}, port={port}, log_config=None, access_log=False)
'''


def _port_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _attendre_demarrage(host: str, port: int, *, timeout_s: float = 10.0) -> None:
    """Poll la socket jusqu'à ce que le serveur réponde, ou abandonne."""
    echeance = time.monotonic() + timeout_s
    derniere_erreur: Exception | None = None
    while time.monotonic() < echeance:
        try:
            httpx.get(f"http://{host}:{port}/", timeout=0.5)
            return
        except httpx.TransportError as exc:
            derniere_erreur = exc
            time.sleep(0.2)
    raise TimeoutError(
        f"le serveur uvicorn n'a pas démarré sous {timeout_s}s : {derniere_erreur}"
    )


@pytest.mark.integration
def test_uvicorn_reel_ne_trace_pas_une_exception_non_rattrapee() -> None:
    """Un vrai process uvicorn, une exception non rattrapée portant une
    adresse et un numéro : ni l'un ni l'autre ne doivent apparaître sur
    stdout, et le mot « Traceback » ne doit pas y figurer non plus.
    """
    host = "127.0.0.1"
    port = _port_libre()
    script = _SCRIPT_SERVEUR.format(
        racine=str(RACINE_DEPOT), adresse=ADRESSE, tel=TEL, host=host, port=port
    )

    processus = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    reponse: httpx.Response | None = None
    try:
        _attendre_demarrage(host, port)
        reponse = httpx.get(f"http://{host}:{port}/fuite-test", timeout=5.0)
    finally:
        processus.terminate()
        try:
            sortie, _ = processus.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            processus.kill()
            sortie, _ = processus.communicate(timeout=5.0)

    assert reponse is not None, (
        "le serveur n'a jamais répondu — voir la sortie ci-dessous :\n" + sortie
    )
    assert reponse.status_code == 500
    assert reponse.json() == {"erreur": "erreur_interne"}

    assert sortie, "le process n'a rien écrit sur stdout : le test ne prouve rien"
    assert ADRESSE not in sortie
    assert TEL not in sortie
    assert "Traceback" not in sortie
    # Le type de l'exception reste journalisé (gestionnaire global) : on ne
    # veut pas perdre la trace de l'INCIDENT, seulement son contenu.
    assert "RuntimeError" in sortie
