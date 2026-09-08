"""Lecture de robots.txt (CLAUDE.md §2 interdiction n°4).

`urllib.robotparser` a été écarté après vérification sur le fichier réel
d'emploidakar : il refuse `/wp-admin/admin-ajax.php` alors que le site
l'autorise explicitement — c'est notre seul point d'entrée — et il autorise
`/resume/` parce qu'il ne retient que le premier groupe `User-agent: *`.
Il nous couperait la source tout en nous laissant aspirer des CV de tiers.

Règle appliquée ici, conforme à l'usage : on fusionne tous les groupes qui
visent notre agent, et pour un chemin donné c'est le motif le plus long qui
tranche, `Allow` l'emportant à longueur égale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class _Regle:
    autorise: bool
    motif: str
    expression: re.Pattern[str]


def _compiler(motif: str) -> re.Pattern[str]:
    """Traduit un motif robots.txt (`*` joker, `$` fin de chaîne) en regex."""
    ancre_fin = motif.endswith("$")
    corps = motif[:-1] if ancre_fin else motif
    regex = "".join(".*" if c == "*" else re.escape(c) for c in corps)
    return re.compile(regex + ("$" if ancre_fin else ""))


class ReglesRobots:
    """Décisions d'accès pour un agent donné, tirées d'un robots.txt."""

    def __init__(self, regles: tuple[_Regle, ...]) -> None:
        self._regles = regles

    @classmethod
    def analyser(cls, texte: str, user_agent: str) -> ReglesRobots:
        agent = user_agent.lower()
        groupes: list[tuple[list[str], list[_Regle]]] = []
        entete_en_cours = False

        for ligne_brute in texte.splitlines():
            ligne = ligne_brute.split("#", 1)[0].strip()
            if not ligne or ":" not in ligne:
                continue
            champ, _, valeur = ligne.partition(":")
            champ, valeur = champ.strip().lower(), valeur.strip()

            if champ == "user-agent":
                # Des `user-agent` consécutifs partagent le même groupe de règles.
                if not entete_en_cours or not groupes:
                    groupes.append(([], []))
                    entete_en_cours = True
                groupes[-1][0].append(valeur.lower())
            elif champ in ("allow", "disallow") and groupes:
                entete_en_cours = False
                if valeur:  # « Disallow: » vide = aucune restriction.
                    groupes[-1][1].append(_Regle(champ == "allow", valeur, _compiler(valeur)))

        # Un groupe visant explicitement notre agent l'emporte sur les groupes `*`.
        cibles = [g for g in groupes if any(t != "*" and t in agent for t in g[0])]
        if not cibles:
            cibles = [g for g in groupes if "*" in g[0]]

        return cls(tuple(regle for _, regles in cibles for regle in regles))

    def autorise(self, url: str) -> bool:
        """Vrai si l'agent a le droit de demander cette URL."""
        decoupe = urlsplit(url)
        chemin = decoupe.path or "/"
        if decoupe.query:
            chemin = f"{chemin}?{decoupe.query}"

        meilleure: _Regle | None = None
        for regle in self._regles:
            if not regle.expression.match(chemin):
                continue
            if meilleure is None or len(regle.motif) > len(meilleure.motif):
                meilleure = regle
            elif len(regle.motif) == len(meilleure.motif) and regle.autorise:
                # À longueur égale, l'autorisation prime.
                meilleure = regle
        return True if meilleure is None else meilleure.autorise
