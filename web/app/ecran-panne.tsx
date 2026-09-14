// Écran de panne réseau ou serveur, partagé par les trois écrans qui
// appellent l'API. Il était copié à l'identique dans chacun d'eux : trois
// copies d'un texte et d'une structure qui doivent rester les mêmes.
//
// Server Component : aucun `'use client'`. Rien ici ne s'exécute chez
// l'utilisateur, et il n'y a aucune raison d'envoyer du JavaScript sur une 3G
// comptée pour afficher deux phrases (§11).
//
// Règle du §11 qu'il porte : on dit quoi faire, jamais ce qui a cassé, et
// l'écran propose toujours une sortie.

import { T } from './textes'

export function EcranPanne({
  reessayerHref,
  retour,
}: {
  /** Où mène « Réessayer » : la page elle-même, paramètres compris. */
  reessayerHref: string
  /** Lien de navigation, quand l'écran en portait un avant la panne. */
  retour?: { href: string; libelle: string }
}) {
  return (
    <main>
      {retour && (
        <nav>
          <a href={retour.href}>{retour.libelle}</a>
        </nav>
      )}
      <p>{T.erreurTemporaire}</p>
      <a href={reessayerHref}>{T.reessayer}</a>
    </main>
  )
}
