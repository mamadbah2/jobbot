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

export type PageOffres = { offres: Offre[]; total: number }

export type CookieSession = { nom: string; valeur: string; maxAge: number }

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

/** Une SEULE IP, jamais la chaîne : les proxys ne s'accordent pas sur
 *  l'extrémité qui fait foi. Avec une seule valeur, la question disparaît. */
export function ipCliente(entetes: Headers): string | null {
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
    return {
      nom,
      valeur: paire.slice(separateur + 1),
      maxAge: maxAge ? Number(maxAge.slice('max-age='.length)) : 0,
    }
  }
  return null
}

/** Attributs du cookie de session, posés par le client web.
 *  Ils doivent refléter ceux de l'API (`poser_cookie` dans routers/auth.py) :
 *  un navigateur n'efface un cookie que si les attributs correspondent. */
export function attributsCookieSession(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: '/',
    maxAge,
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
