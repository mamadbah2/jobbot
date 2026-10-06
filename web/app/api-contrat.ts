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
 *  voie. On ne peut donc pas relever cette borne — c'est le navigateur qui la
 *  fixe, pas nous. Quand elle est quand même atteinte, l'écran le DIT
 *  (`T.brouillonPerdu`) au lieu de rendre les anciennes valeurs sans un mot. */
export const TAILLE_MAX_BROUILLON = 3500

const CHAMPS_TEXTE = ['nom_complet', 'titre', 'mobilite', 'type_contrat'] as const
const CHAMPS_LISTE = ['competences', 'langues', 'secteurs_vises'] as const

/** Ce que le cookie transporte : SEULEMENT les champs que l'utilisateur a
 *  changés par rapport au profil enregistré. Une clé absente veut dire « rien
 *  touché, le serveur a déjà la bonne valeur » ; une clé présente fait foi,
 *  même vide. */
export type BrouillonPartiel = Partial<BrouillonProfil>

/** Le profil enregistré, ramené à la forme du formulaire. Sert de référence au
 *  brouillon : c'est la valeur à laquelle on compare, et celle qu'on recolle. */
export function brouillonDepuisStructured(
  structured: Record<string, unknown> | null,
): BrouillonProfil {
  const s = structured ?? {}
  const texte = (cle: string): string | null => (typeof s[cle] === 'string' ? s[cle] : null)
  const liste = (cle: string): string[] =>
    Array.isArray(s[cle]) ? (s[cle] as unknown[]).filter((v): v is string => typeof v === 'string') : []
  return {
    nom_complet: texte('nom_complet'),
    titre: texte('titre'),
    competences: liste('competences'),
    langues: liste('langues'),
    secteurs_vises: liste('secteurs_vises'),
    mobilite: texte('mobilite'),
    type_contrat: texte('type_contrat'),
  }
}

/** Ce qui a VRAIMENT changé, et rien d'autre.
 *
 *  Le cookie portait jusqu'ici le profil entier : 60 compétences aux libellés
 *  réalistes (« Gestion administrative et financière » fait 36 signes)
 *  franchissent les 3,5 Ko à elles seules, et le brouillon était alors jeté —
 *  dans le scénario MÊME qu'il devait couvrir, puisque le message qui déclenche
 *  l'aller-retour est « vous avez 60 compétences, retirez-en 10 ». L'utilisateur
 *  corrigeait son nom, soumettait, et retrouvait le nom d'avant.
 *
 *  La correction d'un champ simple ne pèse plus que quelques dizaines d'octets :
 *  le reste, le serveur l'a déjà. Un champ vidé volontairement DIFFÈRE de la
 *  référence, donc il entre dans le brouillon et la suppression tient — c'est ce
 *  que l'écran appelait « le brouillon fait foi en bloc », et c'est conservé,
 *  champ par champ cette fois.
 *
 *  Sans référence (profil illisible, API injoignable), tout est considéré comme
 *  changé : on retombe sur l'ancien comportement, borne comprise. */
export function differenceBrouillon(
  saisi: BrouillonProfil,
  reference: BrouillonProfil | null,
): BrouillonPartiel {
  if (reference === null) return { ...saisi }
  const diff: BrouillonPartiel = {}
  for (const champ of CHAMPS_TEXTE) {
    if (saisi[champ] !== reference[champ]) diff[champ] = saisi[champ]
  }
  for (const champ of CHAMPS_LISTE) {
    const a = saisi[champ]
    const b = reference[champ]
    if (a.length !== b.length || a.some((v, i) => v !== b[i])) diff[champ] = a
  }
  return diff
}

/** Recolle le brouillon sur le profil enregistré. Un champ absent du brouillon
 *  reprend la valeur enregistrée — qui est, par construction, celle que
 *  l'utilisateur avait sous les yeux.
 *
 *  Prix assumé : si une analyse de fond se termine entre la soumission et le
 *  rechargement, les champs non modifiés suivent le NOUVEAU profil. C'est
 *  préférable à l'inverse — l'ancien instantané complet aurait masqué en silence
 *  l'analyse que l'utilisateur venait de demander. */
export function appliquerBrouillon(
  brouillon: BrouillonPartiel | null,
  reference: BrouillonProfil,
): BrouillonProfil {
  return brouillon === null ? reference : { ...reference, ...brouillon }
}

/** La saisie en cours, conservée le temps d'un aller-retour d'erreur — même
 *  mécanisme que `COOKIE_ADRESSE` : sans JavaScript, un `redirect` perd ce qui a
 *  été tapé, et un formulaire de profil retapé est un abandon (§11).
 *
 *  BASE64URL, et c'est le point délicat : `cookies().set` de Next encode la
 *  valeur qu'on lui donne, alors que `cookies().get` rend la valeur BRUTE, sans
 *  la décoder. Du JSON posé tel quel revient donc percent-encodé et illisible —
 *  constaté en vrai, le brouillon ne se rappliquait jamais. Base64url n'emploie
 *  aucun caractère qu'`encodeURIComponent` toucherait : ce qui est écrit est
 *  exactement ce qui revient, et la taille mesurée ici est celle du cookie.
 *
 *  `null` = « ça ne tient pas dans un cookie ». L'appelant DOIT alors le dire à
 *  l'utilisateur : c'est la perte silencieuse qu'on a payée une fois. */
export function serialiserBrouillon(donnees: BrouillonPartiel): string | null {
  const encode = Buffer.from(JSON.stringify(donnees), 'utf8').toString('base64url')
  return encode.length > TAILLE_MAX_BROUILLON ? null : encode
}

export function lireBrouillon(valeur: string | undefined): BrouillonPartiel | null {
  if (!valeur) return null
  try {
    const brut = JSON.parse(Buffer.from(valeur, 'base64url').toString('utf8')) as Record<
      string,
      unknown
    >
    if (brut === null || typeof brut !== 'object' || Array.isArray(brut)) return null
    const partiel: BrouillonPartiel = {}
    // Clé ABSENTE et clé à `null` ne veulent pas dire la même chose : l'une
    // signifie « non modifié », l'autre « vidé exprès ». On ne parcourt donc
    // que les clés réellement présentes.
    for (const champ of CHAMPS_TEXTE) {
      if (champ in brut) partiel[champ] = typeof brut[champ] === 'string' ? brut[champ] : null
    }
    for (const champ of CHAMPS_LISTE) {
      if (champ in brut) {
        partiel[champ] = Array.isArray(brut[champ])
          ? (brut[champ] as unknown[]).filter((x): x is string => typeof x === 'string')
          : []
      }
    }
    return partiel
  } catch {
    // Cookie tronqué ou trafiqué : on repart du profil enregistré plutôt que
    // de casser l'écran.
    return null
  }
}

/** Le seul chemin qui lit ce cookie : `/profil` le pose (ses Server Actions
 *  postent sur l'URL de la page) et `/profil` le relit. Sur `path: '/'` il
 *  repartait avec TOUTES les requêtes — les six fragments `/_next/` compris,
 *  soit de l'ordre de 25 Ko d'émission par chargement de page, sur une data
 *  comptée (§11). Et c'est du gaspillage invisible : `mesure-poids.mjs` ne
 *  compte que la descente. */
export const CHEMIN_COOKIE_BROUILLON = '/profil'

export function attributsCookieBrouillon() {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: EN_PROD,
    path: CHEMIN_COOKIE_BROUILLON,
    maxAge: 15 * 60,
  }
}

/** Ce qu'il faut passer à `cookies().delete` pour effacer RÉELLEMENT le
 *  brouillon. Un navigateur n'efface un cookie que si le chemin correspond :
 *  `delete(NOM)` tout court viserait `path: '/'` et laisserait en place celui
 *  qui est posé sur `/profil` — la saisie d'un essai précédent se
 *  rappliquerait indéfiniment. Un test vérifie que les deux chemins
 *  concordent. */
export function effacementCookieBrouillon() {
  return { name: COOKIE_BROUILLON, path: CHEMIN_COOKIE_BROUILLON }
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
