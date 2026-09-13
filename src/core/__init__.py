"""Métier pur : ce package n'importe ni fastapi, ni aiogram, ni starlette.

C'est la condition qui garantit qu'un second client, s'il en revenait un, ne
trouverait aucune règle à réécrire : il n'aurait qu'à traduire `src/core/`,
comme le fait l'API aujourd'hui, seule traductrice. Vérifié par
`tests/test_core_isole.py`.
"""
