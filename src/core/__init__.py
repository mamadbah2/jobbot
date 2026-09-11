"""Métier pur : ce package n'importe ni fastapi, ni aiogram, ni starlette.

C'est la condition qui permet à l'API et au bot d'être deux traductions de la
même règle, et non deux copies. Vérifié par `tests/test_core_isole.py`.
"""
