import { T } from '../textes'

// Page publique et statique : elle ne dépend d'aucune session, un visiteur
// doit pouvoir la lire avant de s'inscrire. Elle décrit le comportement du
// système ; la formulation juridique reste à fournir (§14.4).
export default function PageConfidentialite() {
  return (
    <main>
      <nav>
        <a href="/">{T.retourAccueil}</a>
      </nav>
      <h1>{T.titreConfidentialite}</h1>
      <p>{T.introConfidentialite}</p>

      <h2>{T.titreCollecte}</h2>
      <ul>
        {T.listeCollecte.map((ligne) => (
          <li key={ligne}>{ligne}</li>
        ))}
      </ul>

      <h2>{T.titreFichier}</h2>
      <p>{T.texteFichier}</p>

      <h2>{T.titreTransfert}</h2>
      <p>{T.texteTransfert}</p>

      <h2>{T.titreDuree}</h2>
      <p>{T.texteDuree}</p>

      <h2>{T.titreSupprimer}</h2>
      <p>{T.texteSupprimer}</p>
      <p>
        <a href="/compte/supprimer">{T.lienSupprimer}</a>
      </p>
    </main>
  )
}
