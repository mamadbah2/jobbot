"""Reconnaissance du type réel d'un fichier et extraction de son texte.

Module PUR : aucun réseau, aucune base, aucun framework. C'est lui qui porte le
filtre le plus rentable du produit — tout ce qui peut être refusé l'est ici,
**avant qu'un seul token soit payé** à DeepSeek.

Le type est déduit des octets de tête et jamais de l'extension : un fichier
renommé ne prouve rien. Et un DOCX *étant* une archive ZIP, même les octets de
tête ne suffisent pas à l'affirmer — d'où la distinction entre `CvTypeRefuse`
(les octets de tête disent non) et `CvIllisible` (ils disaient oui, mais le
corps est inexploitable : PDF chiffré, archive tronquée, ZIP sans document).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from src.core.erreurs import CvIllisible, CvSansTexte, CvTypeRefuse

TypeCv = Literal["pdf", "docx", "jpeg", "png"]

_SIGNATURES: tuple[tuple[bytes, TypeCv], ...] = (
    (b"%PDF", "pdf"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    # En dernier : une archive ZIP *peut* être un DOCX, mais aussi n'importe
    # quoi d'autre. C'est `extraire_texte` qui tranche.
    (b"PK\x03\x04", "docx"),
)


def reconnaitre_type(contenu: bytes) -> TypeCv:
    for signature, type_cv in _SIGNATURES:
        if contenu.startswith(signature):
            return type_cv
    raise CvTypeRefuse


def est_une_image(type_cv: TypeCv) -> bool:
    """Une image n'a pas de texte à extraire localement : elle part telle quelle
    au modèle multimodal (spec §8)."""
    return type_cv in ("jpeg", "png")


def _lire_pdf(contenu: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(contenu)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)


def _lire_docx(contenu: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(contenu))
    return "\n".join(p.text for p in document.paragraphs)


@dataclass(frozen=True, slots=True)
class Lecteurs:
    """Lecteurs injectables.

    Les chemins d'échec (PDF chiffré, archive tronquée) se testent en injectant
    un lecteur qui lève, plutôt qu'en fabriquant et maintenant des fichiers
    corrompus dans le dépôt.
    """

    pdf: Callable[[bytes], str]
    docx: Callable[[bytes], str]


LECTEURS_REELS = Lecteurs(pdf=_lire_pdf, docx=_lire_docx)


def extraire_texte(
    contenu: bytes,
    type_cv: TypeCv,
    *,
    minimum: int,
    lecteurs: Lecteurs | None = None,
) -> str:
    """Rend le texte du document, ou lève.

    `minimum` compte les caractères **hors espaces** : un PDF scanné rend
    rarement zéro caractère, il rend quelques artefacts de police. « Vide » ne
    serait donc pas un test suffisant.
    """
    if est_une_image(type_cv):  # pragma: no cover — l'appelant ne doit pas le faire
        raise CvIllisible

    lecteurs = lecteurs or LECTEURS_REELS
    lecteur = lecteurs.pdf if type_cv == "pdf" else lecteurs.docx

    try:
        texte = lecteur(contenu)
    except (CvSansTexte, CvIllisible):
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        # `raise ... from None` et AUCUN détail recopié : le message d'une
        # bibliothèque de lecture peut contenir un fragment du document, et une
        # alerte admin recopie tout son contexte par le réseau (§7).
        raise CvIllisible from None
    except Exception:
        # Une bibliothèque de lecture peut lever n'importe quoi sur un fichier
        # malformé. Un 500 ici serait une porte ouverte : tout échec de lecture
        # est un refus de lecture, pas une panne du service.
        raise CvIllisible from None

    if len(texte.replace(" ", "").strip()) < minimum:
        raise CvSansTexte
    return texte
