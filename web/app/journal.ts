// Une ligne JSON par étape du parcours (CLAUDE.md §11 : « compter et logger
// les abandons à chaque étape »).
//
// JAMAIS d'adresse email, ni aucune autre donnée personnelle : le dépôt porte
// deux tests Python dont c'est l'objet (tests/test_logs_sans_pii.py). L'étape
// suffit à voir où le parcours perd des gens ; l'identité n'y ajoute rien et
// constituerait un fichier de données personnelles.
//
// Cette règle ne tenait qu'à ce commentaire. Elle tient désormais aux types :
// `Etape` et `CodeErreur` sont des unions fermées de littéraux, donc insérer
// un texte libre — et avec lui une adresse — ne compile pas.

// Extension `.ts` explicite, et ce n'est pas un oubli : ce module est chargé
// tel quel par `node --test`, dont le résolveur ESM n'invente aucune
// extension. Sans elle, les tests ne peuvent plus l'importer du tout.
import { CODES_ERREUR, type CodeErreur } from './textes.ts'

/** Les étapes du parcours, dans l'ordre où l'utilisateur les rencontre.
 *
 *  Les deux premières sont émises à l'AFFICHAGE de l'écran, et non à la
 *  soumission d'un formulaire. Sans elles on ne mesure que les gens qui ont
 *  déjà tapé quelque chose, alors que c'est précisément entre « l'écran
 *  s'affiche » et « je tape » qu'on en perd le plus. */
export type Etape =
  | 'vue_connexion'
  | 'vue_code'
  | 'code_demande'
  | 'adresse_refusee'
  | 'nom_demande'
  | 'code_refuse'
  | 'connexion_reussie'
  | 'deconnexion'

/** Le seul détail qu'une étape ait le droit de porter : un code d'erreur de
 *  notre propre API, pris dans une liste fermée. */
type Detail = { code: CodeErreur }

/** Ramène au code connu le plus proche ce que l'API a renvoyé.
 *
 *  Un code inconnu devient `defaut` plutôt que d'être journalisé tel quel :
 *  c'est ce qui interdit qu'une chaîne arbitraire venue du réseau entre dans
 *  les journaux. Même repli que `texteErreur` côté affichage. */
export function codeConnu(brut: string): CodeErreur {
  return (CODES_ERREUR as readonly string[]).includes(brut) ? (brut as CodeErreur) : 'defaut'
}

export function journaliser(etape: Etape, detail?: Detail): void {
  console.log(JSON.stringify({ evenement: 'parcours', etape, ...detail }))
}
