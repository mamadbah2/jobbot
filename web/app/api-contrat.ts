// Aucun import de Next ici : ce module doit être importable par `node --test`.
// Tout ce qui a besoin du contexte de requête vit dans api-client.ts.

export const NOM_COOKIE = process.env.COOKIE_SESSION_NOM ?? 'jobbot_session'
const EN_PROD = process.env.ENVIRONMENT === 'prod'

export type Utilisateur = {
  id: number
  email: string
  nom_complet: string | null
  etat: string
}

export type Offre = {
  id: number
  titre: string
  entreprise: string | null
  lieu: string | null
  type_contrat: string | null
  publiee_le: string | null
  url: string
  methode_candidature: string
}

export type Profil = {
  etat: 'absent' | 'en_attente' | 'en_cours' | 'pret' | 'echec'
  erreur: string | null
  structured: Record<string, unknown> | null
}

export type PageOffres = { offres: Offre[]; total: number }

/** `maxAge` optionnel : absent, le cookie devient un cookie de session, que le
 *  navigateur garde jusqu'à la fermeture. Voir `attributsCookieSession`. */
export type CookieSession = { nom: string; valeur: string; maxAge?: number }

export class ErreurApi extends Error {
  // Champs déclarés explicitement plutôt qu'en propriétés de paramètre : le
  // dépouillement de types natif de Node (mode « strip-only », sans
  // transformation) ne sait pas effacer cette syntaxe de raccourci.
  readonly code: string
  readonly statut: number
  readonly reessayerDans?: number

  constructor(code: string, statut: number, reessayerDans?: number) {
    super(code)
    this.name = 'ErreurApi'
    this.code = code
    this.statut = statut
    this.reessayerDans = reessayerDans
  }
}

/** `true` seulement si un reverse proxy se tient RÉELLEMENT devant `web`.
 *  Fermé par défaut, et c'est le point important : aujourd'hui `web` est publié
 *  en direct sur l'hôte, rien ne se tient devant lui. Le seul `X-Forwarded-For`
 *  que Next puisse alors lire est celui que le client écrit lui-même — le
 *  relayer à l'API rendrait les plafonds par IP de `core/auth/limites.py`
 *  contournables à volonté, en faisant simplement tourner la valeur. */
function derriereProxyParDefaut(): boolean {
  return process.env.WEB_DERRIERE_PROXY === 'true'
}

/** Une SEULE IP, jamais la chaîne : les proxys ne s'accordent pas sur
 *  l'extrémité qui fait foi. Avec une seule valeur, la question disparaît.
 *
 *  Rend `null` tant qu'aucun proxy n'est déclaré. Conséquence assumée en
 *  développement : les plafonds par IP se comportent comme un plafond GLOBAL,
 *  puisque l'API ne voit alors que l'adresse du conteneur `web`. On préfère
 *  l'assumer en le sachant que croire à une protection qui n'existe pas.
 *
 *  `derriereProxy` est un paramètre à valeur par défaut, et non une constante
 *  de module, pour rester testable sans manipuler l'environnement du process. */
export function ipCliente(
  entetes: Headers,
  derriereProxy: boolean = derriereProxyParDefaut(),
): string | null {
  if (!derriereProxy) return null
  const chaine = entetes.get('x-forwarded-for')
  if (!chaine) return null
  const premiere = chaine.split(',')[0]?.trim()
  return premiere ? premiere : null
}

/** Extrait le cookie de session du `Set-Cookie` renvoyé par l'API. */
export function lireCookieSession(entetes: Headers, nom = NOM_COOKIE): CookieSession | null {
  for (const brut of entetes.getSetCookie()) {
    const [paire, ...attributs] = brut.split(';')
    const separateur = paire.indexOf('=')
    if (paire.slice(0, separateur).trim() !== nom) continue
    const maxAge = attributs
      .map((a) => a.trim().toLowerCase())
      .find((a) => a.startsWith('max-age='))
    const duree = maxAge ? Number(maxAge.slice('max-age='.length)) : Number.NaN
    return {
      nom,
      valeur: paire.slice(separateur + 1),
      // `undefined` et non `0` si l'API omettait `Max-Age` : voir
      // `attributsCookieSession` ci-dessous pour pourquoi `0` serait un piège.
      maxAge: Number.isFinite(duree) && duree > 0 ? duree : undefined,
    }
  }
  return null
}

/** Attributs du cookie de session, posés par le client web.
 *  Ils doivent refléter ceux de l'API (`poser_cookie` dans routers/auth.py) :
 *  un navigateur n'efface un cookie que si les attributs correspondent.
 *
 *  Un `maxAge` absent ou nul donne un cookie de SESSION — gardé jusqu'à la
 *  fermeture du navigateur — et surtout PAS un `Max-Age=0`, que le navigateur
 *  supprime aussitôt reçu. Le mode de défaillance évité est le pire qui soit :
 *  connexion « réussie », cookie effacé dans la foulée, rebond immédiat vers
 *  /connexion, et aucune explication pour l'utilisateur. */
export type AttributsCookie = {
  httpOnly: boolean
  sameSite: 'lax'
  secure: boolean
  path: string
  /** Absent = cookie de session. La clé est OMISE, jamais posée à
   *  `undefined` : c'est ce qui distingue « pas de Max-Age » de « Max-Age=0 ». */
  maxAge?: number
}

export function attributsCookieSession(maxAge?: number): AttributsCookie {
  const base: AttributsCookie = {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: '/',
  }
  return maxAge && maxAge > 0 ? { ...base, maxAge } : base
}

/** Les plafonds de `CorrectionProfil` (src/api/schemas/profil.py), recopiés ici
 *  parce qu'ils doivent être connus AVANT l'appel : l'API les refuse avec un 422
 *  de pydantic, dont le corps n'a pas de clé `erreur`, donc l'écran n'afficherait
 *  qu'un « une erreur est survenue » devant lequel l'utilisateur ne peut rien.
 *  Un test Python vérifie que les deux listes sont identiques. */
export const LIMITES_LISTES = {
  competences: 50,
  langues: 20,
  secteurs_vises: 20,
} as const

export type ChampListe = keyof typeof LIMITES_LISTES

/** Ce que l'écran de profil envoie, et ce qu'il doit savoir reconstituer après
 *  une erreur : exactement les champs du formulaire. */
export type BrouillonProfil = {
  nom_complet: string | null
  titre: string | null
  competences: string[]
  langues: string[]
  secteurs_vises: string[]
  mobilite: string | null
  type_contrat: string | null
}

export type ListeTropLongue = { champ: ChampListe; saisi: number; limite: number }

/** La PREMIÈRE liste qui dépasse, ou `null`. On en nomme une seule : le message
 *  reste court (§11) et l'utilisateur corrige celle-là, puis la suivante. */
export function listeTropLongue(donnees: BrouillonProfil): ListeTropLongue | null {
  for (const champ of Object.keys(LIMITES_LISTES) as ChampListe[]) {
    const limite = LIMITES_LISTES[champ]
    const saisi = donnees[champ].length
    if (saisi > limite) return { champ, saisi, limite }
  }
  return null
}

export const COOKIE_BROUILLON = 'jobbot_profil_brouillon'

/** Au-delà, le cookie est abandonné : un navigateur en jette un de plus de 4 Ko,
 *  et un cookie jeté en silence ferait perdre la saisie SANS que personne ne le
 *  voie. Mieux vaut renoncer en le sachant — l'écran affiche alors le profil
 *  enregistré, et le message qui dit quoi corriger reste là. */
export const TAILLE_MAX_BROUILLON = 3500

/** La saisie en cours, conservée le temps d'un aller-retour d'erreur — même
 *  mécanisme que `COOKIE_ADRESSE` : sans JavaScript, un `redirect` perd ce qui a
 *  été tapé, et un formulaire de profil retapé est un abandon (§11). */
export function serialiserBrouillon(donnees: BrouillonProfil): string | null {
  const encode = encodeURIComponent(JSON.stringify(donnees))
  return encode.length > TAILLE_MAX_BROUILLON ? null : encode
}

export function lireBrouillon(valeur: string | undefined): BrouillonProfil | null {
  if (!valeur) return null
  try {
    const brut = JSON.parse(decodeURIComponent(valeur)) as Partial<BrouillonProfil>
    const liste = (v: unknown): string[] =>
      Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
    const texte = (v: unknown): string | null => (typeof v === 'string' ? v : null)
    return {
      nom_complet: texte(brut.nom_complet),
      titre: texte(brut.titre),
      competences: liste(brut.competences),
      langues: liste(brut.langues),
      secteurs_vises: liste(brut.secteurs_vises),
      mobilite: texte(brut.mobilite),
      type_contrat: texte(brut.type_contrat),
    }
  } catch {
    // Cookie tronqué ou trafiqué : on repart du profil enregistré plutôt que
    // de casser l'écran.
    return null
  }
}

export function attributsCookieBrouillon() {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: '/',
    maxAge: 15 * 60,
  }
}

export const COOKIE_ADRESSE = 'jobbot_adresse_en_cours'

/** L'adresse en cours de vérification : elle transite par cookie et JAMAIS par
 *  l'URL, qui la ferait entrer dans l'historique, le Referer et les journaux. */
export function attributsCookieAdresse() {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: '/',
    maxAge: 15 * 60,
  }
}
