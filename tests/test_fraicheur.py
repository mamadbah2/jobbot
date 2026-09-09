"""Rafraîchissement à la demande, déclenché par la visite d'un utilisateur.

Deux dangers que ce module doit écarter (CLAUDE.md §2 interdiction n°4) :

- la ruée : dix utilisateurs à 8 h du matin ne doivent pas lancer dix passes
  concurrentes sur le même domaine — le limiteur de débit vit en mémoire et ne
  les verrait pas se marcher dessus ; un bannissement d'IP Cloudflare
  emporterait TOUTES les sources ;
- la boucle du dimanche : quand le site ne publie rien, la fraîcheur se mesure
  à la dernière PASSE réussie, jamais à la date de la dernière offre — sinon
  chaque visite relance une passe toute la journée pour zéro offre.
"""

from __future__ import annotations

from typing import Any

from src.ingest.fraicheur import (
    demander_rafraichissement,
    liberer_verrou,
    marquer_passe_reussie,
)

SOURCE = "emploidakar"


class RedisFactice:
    """Redis en mémoire, avec horloge simulée pour les TTL."""

    def __init__(self) -> None:
        self.donnees: dict[str, tuple[str, float | None]] = {}
        self.maintenant = 0.0

    def _expire(self) -> None:
        for cle, (_, echeance) in list(self.donnees.items()):
            if echeance is not None and echeance <= self.maintenant:
                del self.donnees[cle]

    async def get(self, name: str) -> Any:
        self._expire()
        entree = self.donnees.get(name)
        return entree[0] if entree else None

    async def set(
        self, name: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> Any:
        self._expire()
        if nx and name in self.donnees:
            return None
        self.donnees[name] = (value, self.maintenant + ex if ex else None)
        return True

    async def delete(self, *names: str) -> Any:
        for n in names:
            self.donnees.pop(n, None)
        return len(names)


async def test_premiere_visite_declenche_un_rafraichissement() -> None:
    decision = await demander_rafraichissement(
        RedisFactice(), SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    assert decision.rafraichir is True


async def test_une_passe_recente_ne_redeclenche_rien() -> None:
    """Le critère est la dernière PASSE, pas la date de la dernière offre."""
    cache = RedisFactice()
    await marquer_passe_reussie(cache, SOURCE, fraicheur_secondes=1800)
    decision = await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    assert decision.rafraichir is False
    assert decision.raison == "passe_recente"


async def test_un_dimanche_sans_publication_ne_boucle_pas() -> None:
    """Aucune offre nouvelle, mais la passe a réussi : on ne relance pas."""
    cache = RedisFactice()
    await marquer_passe_reussie(cache, SOURCE, fraicheur_secondes=1800)
    for _ in range(50):
        decision = await demander_rafraichissement(
            cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
        )
        assert decision.rafraichir is False


async def test_la_ruee_ne_lance_qu_une_seule_passe() -> None:
    """Dix visites simultanées, une seule passe. C'est le garde-fou de §2.4."""
    cache = RedisFactice()
    decisions = [
        await demander_rafraichissement(
            cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
        )
        for _ in range(10)
    ]
    assert sum(d.rafraichir for d in decisions) == 1
    assert [d.raison for d in decisions if not d.rafraichir] == ["passe_deja_en_cours"] * 9


async def test_on_relance_une_fois_la_fraicheur_expiree() -> None:
    cache = RedisFactice()
    await marquer_passe_reussie(cache, SOURCE, fraicheur_secondes=1800)
    cache.maintenant += 1801
    decision = await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    assert decision.rafraichir is True


async def test_un_verrou_abandonne_se_libere_tout_seul() -> None:
    """Si une passe plante sans libérer, le TTL débloque la source."""
    cache = RedisFactice()
    await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    cache.maintenant += 301
    decision = await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    assert decision.rafraichir is True


async def test_liberer_le_verrou_autorise_une_nouvelle_passe() -> None:
    cache = RedisFactice()
    await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    await liberer_verrou(cache, SOURCE)
    decision = await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    assert decision.rafraichir is True


async def test_les_sources_ne_se_bloquent_pas_entre_elles() -> None:
    cache = RedisFactice()
    await demander_rafraichissement(
        cache, SOURCE, fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    autre = await demander_rafraichissement(
        cache, "reliefweb", fraicheur_secondes=1800, duree_verrou_secondes=300
    )
    assert autre.rafraichir is True


# --- Orchestration : l'utilisateur ne doit jamais attendre la passe ---


async def test_l_utilisateur_n_attend_pas_la_fin_de_la_passe() -> None:
    """§11 : data chère et 3G instable. On rend la main tout de suite."""
    import asyncio

    from src.ingest.fraicheur import rafraichir_si_necessaire

    cache = RedisFactice()
    terminee = asyncio.Event()

    async def passe_lente() -> None:
        await terminee.wait()

    taches: list[Any] = []
    decision = await rafraichir_si_necessaire(
        cache,
        SOURCE,
        fraicheur_secondes=1800,
        duree_verrou_secondes=300,
        executer_passe=passe_lente,
        planifier=lambda coro: taches.append(asyncio.ensure_future(coro)),
    )
    assert decision.rafraichir is True  # rendu AVANT la fin de la passe
    terminee.set()
    await asyncio.gather(*taches)


async def test_une_passe_reussie_pose_le_repere_et_libere_le_verrou() -> None:
    import asyncio

    from src.ingest.fraicheur import rafraichir_si_necessaire

    cache = RedisFactice()

    async def passe_ok() -> None:
        return None

    taches: list[Any] = []
    await rafraichir_si_necessaire(
        cache,
        SOURCE,
        fraicheur_secondes=1800,
        duree_verrou_secondes=300,
        executer_passe=passe_ok,
        planifier=lambda coro: taches.append(asyncio.ensure_future(coro)),
    )
    await asyncio.gather(*taches)
    assert await cache.get(f"jobbot:ingest:{SOURCE}:derniere_passe") is not None
    assert await cache.get(f"jobbot:ingest:{SOURCE}:verrou") is None


async def test_une_passe_en_echec_ne_se_fait_pas_passer_pour_fraiche() -> None:
    """Sinon on attendrait 30 min avant de retenter, sur une base périmée."""
    import asyncio

    from src.ingest.fraicheur import rafraichir_si_necessaire

    cache = RedisFactice()

    async def passe_ko() -> None:
        raise RuntimeError("site injoignable")

    taches: list[Any] = []
    await rafraichir_si_necessaire(
        cache,
        SOURCE,
        fraicheur_secondes=1800,
        duree_verrou_secondes=300,
        executer_passe=passe_ko,
        planifier=lambda coro: taches.append(asyncio.ensure_future(coro)),
    )
    await asyncio.gather(*taches, return_exceptions=True)
    assert await cache.get(f"jobbot:ingest:{SOURCE}:derniere_passe") is None
    assert await cache.get(f"jobbot:ingest:{SOURCE}:verrou") is None


async def test_aucune_passe_planifiee_si_la_base_est_fraiche() -> None:
    from src.ingest.fraicheur import rafraichir_si_necessaire

    cache = RedisFactice()
    await marquer_passe_reussie(cache, SOURCE, fraicheur_secondes=1800)
    lancees = 0

    async def passe() -> None:
        nonlocal lancees
        lancees += 1

    decision = await rafraichir_si_necessaire(
        cache,
        SOURCE,
        fraicheur_secondes=1800,
        duree_verrou_secondes=300,
        executer_passe=passe,
        planifier=lambda coro: coro.close(),
    )
    assert decision.rafraichir is False
    assert lancees == 0
