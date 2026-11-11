import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

import { moi, profil } from '../api-client'
import {
  COOKIE_BROUILLON,
  LIMITES_LISTES,
  appliquerBrouillon,
  brouillonDepuisStructured,
  lireBrouillon,
  listeTropLongue,
  type ChampListe,
} from '../api-contrat'
import { EcranPanne } from '../ecran-panne'
import { journaliser } from '../journal'
import { CONTRATS, REGIONS, SECTEURS, T, texteErreur, texteTropDeValeurs } from '../textes'
import { enregistrerProfil, envoyerCv } from './actions'

type Ligne = Record<string, string | null | undefined>

export default async function PageProfil({
  searchParams,
}: {
  searchParams: Promise<{
    erreur?: string
    redeposer?: string
    trop?: string
    saisi?: string
    brouillon?: string
  }>
}) {
  const panne = (
    <EcranPanne reessayerHref="/profil" retour={{ href: '/offres', libelle: T.lienOffres }} />
  )

  let utilisateur
  let etat
  try {
    utilisateur = await moi()
    etat = utilisateur ? await profil() : null
  } catch {
    return panne
  }
  // Session périmée : par la route qui efface le cookie, sinon il repart à
  // chaque requête pour se faire refuser à chaque fois.
  if (!utilisateur || !etat) redirect('/connexion/expiree')

  const { erreur, redeposer, trop, saisi, brouillon: sortBrouillon } = await searchParams
  // La saisie n'a pas pu être conservée : on le dit, au lieu de rendre les
  // anciennes valeurs sans un mot.
  const brouillonPerdu = sortBrouillon === 'perdu'
  // Une liste trop longue a son propre message, qui nomme la liste et le
  // nombre à retirer : le code générique ne dirait rien d'actionnable.
  const messageTrop =
    trop && trop in LIMITES_LISTES
      ? texteTropDeValeurs(trop, Number(saisi) || 0, LIMITES_LISTES[trop as ChampListe])
      : null
  const message = messageTrop ?? texteErreur(erreur) ?? texteErreur(etat.erreur ?? undefined)

  // Rechargement par balise HTML : aucun JavaScript, donc ça marche même quand
  // le runtime Next n'arrive jamais (3G qui coupe), et l'analyse continue si
  // l'utilisateur ferme son navigateur.
  // `en_attente` : le dépôt est enregistré et attend une place d'analyse
  // (plafond de simultanéité côté API). `en_cours` : DeepSeek lit le CV. Les
  // deux attendent, mais on ne promet pas une lecture qui n'a pas commencé.
  if (etat.etat === 'en_cours' || etat.etat === 'en_attente') {
    // Pas de journal ici : la page se recharge toute les 5 s, huit « vues »
    // pour une seule personne ruineraient la mesure d'abandon (§11).
    return (
      <main>
        <meta httpEquiv="refresh" content="5" />
        <nav>
          <a href="/offres">{T.lienOffres}</a> · <a href="/compte">{T.lienCompte}</a>
        </nav>
        <h1>{T.titreProfil}</h1>
        <p>{etat.etat === 'en_attente' ? T.analyseEnAttente : T.analyseEnCours}</p>
      </main>
    )
  }

  // `absent`, `pret` ou `echec` : ici seulement, une vue = une personne.
  journaliser(`vue_profil_${etat.etat}`)

  // `echec` AVEC un profil enregistré : c'est un REDÉPÔT qui a échoué. Le profil
  // précédent est toujours valide et doit rester visible — le masquer ferait
  // croire à l'utilisateur qu'il a tout perdu. Le message d'échec s'affiche à
  // côté, et le lien « déposer un autre CV » reste la sortie.
  if ((etat.etat === 'pret' || etat.etat === 'echec') && etat.structured && !redeposer) {
    const s = etat.structured
    const lignes = (cle: string): Ligne[] => (Array.isArray(s[cle]) ? (s[cle] as Ligne[]) : [])
    const experiences = lignes('experiences')
    const formations = lignes('formations')

    // La saisie d'une tentative refusée prime sur ce qui est enregistré : sans
    // JavaScript, c'est la seule façon de ne pas la perdre au `redirect`. Le
    // cookie ne porte QUE les champs modifiés (un profil entier n'entre pas
    // dans les 4 Ko d'un cookie dès 60 compétences) ; les autres se recollent
    // ici depuis le profil enregistré. Un champ vidé par l'utilisateur diffère
    // de l'enregistré, donc il est dans le brouillon et reste vide : une
    // suppression volontaire n'est jamais annulée.
    const enregistre = brouillonDepuisStructured(s)
    const valeurs = appliquerBrouillon(
      lireBrouillon((await cookies()).get(COOKIE_BROUILLON)?.value),
      enregistre,
    )

    const secteurs = valeurs.secteurs_vises
    // Ce que le formulaire ne sait pas afficher (secteur en texte libre
    // extrait du CV, région hors liste) est montré et conservé : l'écraser
    // en silence ferait perdre à l'utilisateur ce qu'il ne voit jamais.
    const secteursHorsListe = secteurs.filter((x) => !SECTEURS.includes(x))
    const mobilite = valeurs.mobilite ?? ''
    const regions = mobilite && !REGIONS.includes(mobilite) ? [mobilite, ...REGIONS] : REGIONS
    const typeContrat = valeurs.type_contrat ?? ''
    const contrats = typeContrat && !CONTRATS.includes(typeContrat) ? [typeContrat, ...CONTRATS] : CONTRATS

    // Un CV peut donner plus de compétences que l'API n'en accepte. On ne
    // tronque pas en silence — l'utilisateur ne saurait pas lesquelles ont
    // disparu : on les montre toutes et on lui dit, AVANT qu'il soumette,
    // combien en retirer.
    const debordement = listeTropLongue(valeurs)
    const avertissement =
      message ??
      (debordement
        ? texteTropDeValeurs(debordement.champ, debordement.saisi, debordement.limite)
        : null)

    return (
      <main>
        <nav>
          <a href="/offres">{T.lienOffres}</a> · <a href="/compte">{T.lienCompte}</a>
        </nav>
        <h1>{T.titreValidation}</h1>
        <p>{T.aideValidation}</p>
        {avertissement && <p className="erreur">{avertissement}</p>}
        {/* En plus de l'avertissement, jamais à sa place : l'utilisateur doit
            savoir À LA FOIS quoi corriger et que sa saisie n'a pas été gardée. */}
        {brouillonPerdu && <p className="erreur">{T.brouillonPerdu}</p>}
        <section className="offre">
          <h2>{T.titreLecture}</h2>
          {experiences.length === 0 && formations.length === 0 ? (
            <p className="meta">{T.aucuneLecture}</p>
          ) : (
            <ul>
              {experiences.map((e, i) => (
                <li key={`e${i}`} className="meta">
                  {e.poste}{e.entreprise ? ` — ${e.entreprise}` : ''} {e.periode ? `(${e.periode})` : ''}
                </li>
              ))}
              {formations.map((f, i) => (
                <li key={`f${i}`} className="meta">
                  {f.diplome}{f.etablissement ? ` — ${f.etablissement}` : ''} {f.annee ? `(${f.annee})` : ''}
                </li>
              ))}
            </ul>
          )}
          <p className="issue-secours">
            {T.siFaux} <a href="/profil?redeposer=1">{T.redeposerCv}</a>
          </p>
        </section>

        <form action={enregistrerProfil}>
          <label htmlFor="nom_complet">{T.champNomProfil}</label>
          <input id="nom_complet" name="nom_complet" defaultValue={valeurs.nom_complet ?? ''} />

          <label htmlFor="titre">{T.champTitre}</label>
          <input id="titre" name="titre" defaultValue={valeurs.titre ?? ''} />

          <label htmlFor="competences">{T.champCompetences}</label>
          <input
            id="competences"
            name="competences"
            defaultValue={valeurs.competences.join(', ')}
          />

          <label htmlFor="langues">{T.champLangues}</label>
          <input id="langues" name="langues" defaultValue={valeurs.langues.join(', ')} />

          <fieldset>
            <legend>{T.legendeSecteurs}</legend>
            {[...SECTEURS, ...secteursHorsListe].map((secteur) => (
              <label key={secteur}>
                <input
                  type="checkbox"
                  name="secteurs"
                  value={secteur}
                  defaultChecked={secteurs.includes(secteur)}
                />{' '}
                {secteur}
              </label>
            ))}
          </fieldset>

          <label htmlFor="region">{T.champRegion}</label>
          <select id="region" name="region" defaultValue={mobilite}>
            <option value="">{T.choisir}</option>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>

          <label htmlFor="contrat">{T.champContrat}</label>
          <select id="contrat" name="contrat" defaultValue={typeContrat}>
            <option value="">{T.choisir}</option>
            {contrats.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>

          <button type="submit">{T.boutonValider}</button>
        </form>

      </main>
    )
  }

  // `absent`, `echec`, et `pret` avec `?redeposer=1` : un formulaire de dépôt.
  return (
    <main>
      <nav>
        <a href="/offres">{T.lienOffres}</a> · <a href="/compte">{T.lienCompte}</a>
      </nav>
      <h1>{T.titreProfil}</h1>
      <p>{T.aideDepot}</p>
      {message && <p className="erreur">{message}</p>}
      <form action={envoyerCv} encType="multipart/form-data">
        <label htmlFor="fichier">{T.champFichier}</label>
        <input id="fichier" name="fichier" type="file" accept=".pdf,.docx,image/jpeg,image/png" required />
        <p className="meta">{T.avertissementDeepSeek}</p>
        <button type="submit">{T.boutonDeposer}</button>
      </form>
      <p className="issue-secours">
        <a href="/confidentialite">{T.lienConfidentialite}</a>
      </p>
    </main>
  )
}
