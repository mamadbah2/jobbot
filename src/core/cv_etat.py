"""Ce que l'écran doit montrer, à partir de ce que la base dit.

Si `api` redémarre en pleine analyse, rien ne reprend le travail : le profil
reste `en_cours` pour toujours. Plutôt qu'un balayeur de tâches zombies — un
processus de plus à faire tourner, à surveiller et à déboguer un jour de panne —
l'écran traite une analyse trop vieille comme un échec et propose de redéposer.

Fonction PURE, horloge injectée : la règle se teste sans base et sans attendre.
"""

from __future__ import annotations

from datetime import datetime

ANALYSE_INTERROMPUE = "analyse_interrompue"


def etat_affiche(
    parse_etat: str,
    parse_demarre_le: datetime | None,
    *,
    maintenant: datetime,
    delai_max_secondes: int,
) -> tuple[str, str | None]:
    """Rend `(état, code d'erreur)` tels que le client doit les voir."""
    if parse_etat != "en_cours":
        return parse_etat, None
    if parse_demarre_le is None:
        # `en_cours` sans date de départ : incohérent, donc suspect. On préfère
        # proposer de redéposer plutôt que de faire attendre indéfiniment.
        return "echec", ANALYSE_INTERROMPUE
    age = (maintenant - parse_demarre_le).total_seconds()
    if age > delai_max_secondes:
        return "echec", ANALYSE_INTERROMPUE
    return "en_cours", None
