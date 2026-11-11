"""Config : valeurs par défaut, surcharges d'environnement, DSN."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import MOT_DE_PASSE_DEV_PUBLIC, Settings, get_settings

RACINE = Path(__file__).resolve().parent.parent


def _vider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Seuls les noms que `Settings` lit, et pas toutes les variables en
    # majuscules : effacer PATH, HOME ou LANG le temps d'un test est
    # gratuitement dangereux, même si monkeypatch les restaure ensuite.
    for champ in Settings.model_fields:
        monkeypatch.delenv(champ.upper(), raising=False)
    get_settings.cache_clear()


def test_env_example_suffit_a_demarrer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Critère de la Phase 0 (CLAUDE.md §12) : la pile démarre à partir du seul
    `.env.example`. `POSTGRES_PASSWORD` est désormais obligatoire (§14.11) ;
    ce test garantit que `.env.example` la fournit, et fournira toute valeur
    obligatoire ajoutée plus tard."""
    _vider_env(monkeypatch)
    monkeypatch.setitem(Settings.model_config, "env_file", RACINE / ".env.example")
    reglages = Settings()  # type: ignore[call-arg]
    assert reglages.environment == "dev"


def test_mot_de_passe_postgres_obligatoire(monkeypatch: pytest.MonkeyPatch) -> None:
    """§14.11 : sans valeur par défaut. L'ancienne valeur par défaut était publiée
    dans `.env.example` (dépôt public) : un déploiement qui oubliait la variable
    démarrait avec un mot de passe connu de tous, sans que rien ne crie."""
    _vider_env(monkeypatch)
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings()  # type: ignore[call-arg]


def test_mot_de_passe_postgres_vide_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """`POSTGRES_PASSWORD=` (ligne copiée sans valeur) vaut une absence."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    get_settings.cache_clear()
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        get_settings()


def _env_prod_valide(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod complète, sauf le point testé : isole le garde-fou du mot de passe
    des deux autres garde-fous de prod (JWT_SECRET, fournisseur console)."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("FOURNISSEUR_COURRIEL", "fournisseur_reel")
    get_settings.cache_clear()


def test_mot_de_passe_de_dev_refuse_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """§14.11 : la valeur de `.env.example` est publique, donc interdite en prod."""
    _env_prod_valide(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", MOT_DE_PASSE_DEV_PUBLIC)
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        get_settings()


def test_mot_de_passe_propre_accepte_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    _env_prod_valide(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "un-vrai-mot-de-passe-genere")
    assert get_settings().is_prod


def test_mot_de_passe_de_dev_accepte_en_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """En dev, la valeur publique reste permise : Postgres n'écoute que sur
    127.0.0.1 (docker-compose.yml) et c'est celle de `.env.example`."""
    monkeypatch.setenv("POSTGRES_PASSWORD", MOT_DE_PASSE_DEV_PUBLIC)
    get_settings.cache_clear()
    assert get_settings().environment == "dev"


def test_constante_alignee_sur_env_example() -> None:
    """Si `.env.example` change de mot de passe sans que la constante suive,
    le garde-fou de prod ne protège plus rien, en silence."""
    texte = (RACINE / ".env.example").read_text(encoding="utf-8")
    assert f"POSTGRES_PASSWORD={MOT_DE_PASSE_DEV_PUBLIC}" in texte.splitlines()


def test_defauts_metier() -> None:
    """Les plafonds du §6 et du §8 ont les valeurs du brief par défaut."""
    s = get_settings()
    assert s.pro_monthly_quota == 25
    assert s.free_trial_applications == 2
    assert s.free_daily_alerts == 5
    assert s.subscription_price_fcfa == 1000
    assert s.subscription_days == 30
    assert s.grace_period_days == 3
    assert s.max_applications_per_job == 15


def test_quota_surchargeable_par_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """§6 : le quota Pro est un plafond de coût, il doit être configurable."""
    monkeypatch.setenv("PRO_MONTHLY_QUOTA", "40")
    get_settings.cache_clear()
    assert get_settings().pro_monthly_quota == 40


def test_delai_scraping_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    """§2, interdiction n°4 : jamais moins de 3 s entre deux requêtes."""
    monkeypatch.setenv("SCRAPER_DELAY_SECONDS", "0.5")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_database_url_utilise_asyncpg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "d")
    get_settings.cache_clear()
    assert get_settings().database_url == "postgresql+asyncpg://u:p@h:5433/d"


def test_secrets_non_exposes_dans_repr() -> None:
    """Aucun secret ne doit fuiter dans les logs via un repr de config."""
    s = get_settings()
    assert "motdepasse_test" not in repr(s)


def test_proxy_ips_de_confiance_vide_par_defaut() -> None:
    """Vide = on ne fait confiance à personne, `request.client.host` reste fiable."""
    assert get_settings().proxy_ips_de_confiance == ""


def test_proxy_ips_de_confiance_surchargeable_par_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXY_IPS_DE_CONFIANCE", "10.0.0.1,10.0.0.2")
    get_settings.cache_clear()
    assert get_settings().proxy_ips_de_confiance == "10.0.0.1,10.0.0.2"


def test_jwt_secret_absent_refuse_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un secret vide en production permettrait de forger n'importe quel jeton."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_jwt_secret_absent_tolere_en_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.jwt_secret.get_secret_value()  # secret éphémère généré


def test_jwt_secret_trop_court_refuse_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Amendement tâche 5 : un secret court se retrouve par force brute."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "trop_court")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_jwt_secret_de_32_caracteres_accepte_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    # Sans quoi le défaut FOURNISSEUR_COURRIEL=console refuse le démarrage en
    # prod (test dédié plus bas) : ce n'est pas ce que ce test vérifie.
    monkeypatch.setenv("FOURNISSEUR_COURRIEL", "un_fournisseur_reel")
    get_settings.cache_clear()
    assert get_settings().jwt_secret.get_secret_value() == "a" * 32


def test_fournisseur_courriel_console_refuse_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """`console` journalise le code en clair (§2, interdiction n°2) : c'est la
    valeur par défaut, donc rien ne devait l'empêcher de partir en prod par oubli."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.delenv("FOURNISSEUR_COURRIEL", raising=False)  # garde le défaut "console"
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_fournisseur_courriel_console_tolere_en_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("FOURNISSEUR_COURRIEL", raising=False)
    get_settings.cache_clear()
    assert get_settings().fournisseur_courriel == "console"


def test_fournisseur_courriel_reel_accepte_en_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("FOURNISSEUR_COURRIEL", "un_fournisseur_reel")
    get_settings.cache_clear()
    assert get_settings().fournisseur_courriel == "un_fournisseur_reel"


def test_garde_fous_auth_valeurs_par_defaut() -> None:
    settings = get_settings()
    assert settings.code_ttl_secondes == 300
    assert settings.auth_cooldown_secondes == 60
    assert settings.auth_envois_par_heure == 3
    assert settings.auth_envois_par_jour == 10
    assert settings.auth_envois_par_ip_heure == 10
    assert settings.auth_plafond_global_jour == 500
    assert settings.jwt_duree_jours == 30


def test_cookie_secure_suit_l_environnement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    get_settings.cache_clear()
    assert get_settings().cookie_session_secure is False
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "secret_de_test_avec_trente_deux_caracteres_ou_plus")
    # Sans quoi le défaut FOURNISSEUR_COURRIEL=console refuse le démarrage en
    # prod (test dédié plus haut) : ce n'est pas ce que ce test vérifie.
    monkeypatch.setenv("FOURNISSEUR_COURRIEL", "un_fournisseur_reel")
    get_settings.cache_clear()
    assert get_settings().cookie_session_secure is True


def test_secret_jwt_absent_du_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le secret ne doit pas fuiter dans les logs via model_dump()."""
    monkeypatch.setenv("JWT_SECRET", "ne_doit_pas_apparaitre")
    get_settings.cache_clear()
    assert "ne_doit_pas_apparaitre" not in str(get_settings().model_dump())


def test_les_reglages_du_cv_ont_des_defauts_surs() -> None:
    """Un déploiement qui oublie ces variables doit rester borné, pas illimité."""
    r = get_settings()
    assert r.deepseek_modele == "deepseek-flash"
    assert r.cv_taille_max_mo == 5
    assert r.cv_texte_min_caracteres == 200
    assert r.cv_analyses_par_jour == 5
    assert r.cv_image_ttl_secondes == 600
    assert r.cv_analyse_delai_max_secondes == 300


def test_la_cle_deepseek_est_un_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un `str` nu finirait dans un `repr` de Settings, donc potentiellement
    dans une trace d'erreur ou un log de démarrage."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-de-test")
    get_settings.cache_clear()
    r = get_settings()
    assert "sk-secret-de-test" not in repr(r)
    assert r.deepseek_api_key.get_secret_value() == "sk-secret-de-test"
