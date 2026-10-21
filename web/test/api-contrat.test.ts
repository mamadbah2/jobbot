import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  ipCliente,
  lireCookieSession,
  attributsCookieSession,
  attributsCookieBrouillon,
  effacementCookieBrouillon,
  appliquerBrouillon,
  brouillonDepuisStructured,
  differenceBrouillon,
  listeTropLongue,
  lireBrouillon,
  serialiserBrouillon,
  COOKIE_BROUILLON,
  LIMITES_LISTES,
} from '../app/api-contrat.ts'
import {
  etatLisible,
  texteErreur,
  texteTropDeValeurs,
  CODES_ERREUR,
  ERREURS,
} from '../app/textes.ts'
import { codeConnu } from '../app/journal.ts'

test("ipCliente ne garde que la première IP de la chaîne", () => {
  const entetes = new Headers({ 'x-forwarded-for': '41.82.1.9, 172.18.0.4, 10.0.0.2' })
  assert.equal(ipCliente(entetes, true), '41.82.1.9')
})

test("ipCliente rend null quand l'en-tête est absent", () => {
  assert.equal(ipCliente(new Headers(), true), null)
})

test("ipCliente ignore le X-Forwarded-For tant qu'aucun proxy n'est déclaré", () => {
  // Le cas RÉEL aujourd'hui : rien ne se tient devant `web`. L'en-tête ne peut
  // donc venir que du client lui-même ; le relayer laisserait n'importe qui
  // contourner les plafonds par IP en faisant tourner la valeur.
  const forge = new Headers({ 'x-forwarded-for': '1.2.3.4' })
  assert.equal(ipCliente(forge, false), null)
})

test('lireCookieSession extrait la valeur et le max-age', () => {
  const entetes = new Headers()
  entetes.append(
    'set-cookie',
    'jobbot_session=abc.def.ghi; Max-Age=2592000; Path=/; HttpOnly; SameSite=lax',
  )
  const session = lireCookieSession(entetes)
  assert.equal(session?.valeur, 'abc.def.ghi')
  assert.equal(session?.maxAge, 2592000)
})

test('lireCookieSession ignore un cookie qui ne porte pas le bon nom', () => {
  const entetes = new Headers()
  entetes.append('set-cookie', 'autre=valeur; Path=/')
  assert.equal(lireCookieSession(entetes), null)
})

test('le cookie de session reste httpOnly et SameSite=lax', () => {
  const a = attributsCookieSession(2592000)
  assert.equal(a.httpOnly, true)
  assert.equal(a.sameSite, 'lax')
  assert.equal(a.path, '/')
  assert.equal(a.maxAge, 2592000)
})

test('chaque code d’erreur de l’API a une phrase, et réciproquement', () => {
  // Les deux sens comptent. CODES_ERREUR gouverne ce qui a le droit d'entrer
  // dans les journaux (journal.ts) ; ERREURS gouverne ce que l'utilisateur
  // lit. Une liste qui prend de l'avance sur l'autre casse l'un des deux en
  // silence.
  for (const code of CODES_ERREUR) {
    assert.ok(ERREURS[code], `code sans phrase : ${code}`)
  }
  for (const code of Object.keys(ERREURS)) {
    assert.ok(
      (CODES_ERREUR as readonly string[]).includes(code),
      `phrase sans code déclaré : ${code}`,
    )
  }
})

test('un code inconnu tombe sur le message par défaut, jamais sur le code brut', () => {
  assert.equal(texteErreur('code_invente_par_un_attaquant'), ERREURS.defaut)
  assert.equal(texteErreur(undefined), null)
})

test('codeConnu refuse une chaîne arbitraire venue du réseau', () => {
  // La garde qui empêche une adresse email d'entrer dans les journaux si un
  // jour l'API renvoyait un code inattendu.
  assert.equal(codeConnu('code_invalide'), 'code_invalide')
  assert.equal(codeConnu('awa@example.sn'), 'defaut')
  assert.equal(codeConnu(''), 'defaut')
})

test("chaque état de users.state a un libellé, et jamais la valeur brute", () => {
  // La liste fait foi dans USER_STATES (src/db/models.py). Si elle y gagne une
  // valeur sans que ce fichier suive, le repli parle encore français.
  for (const etat of ['onboarding', 'active', 'blocked']) {
    const libelle = etatLisible(etat)
    assert.ok(libelle, `état sans libellé : ${etat}`)
    assert.notEqual(libelle, etat, `libellé brut affiché pour ${etat}`)
  }
  assert.equal(etatLisible('valeur_ajoutee_plus_tard'), 'État inconnu')
})

test("un Set-Cookie sans Max-Age donne un cookie de session, jamais un Max-Age=0", () => {
  // Le piège évité : un cookie `Max-Age=0` est supprimé aussitôt reçu par le
  // navigateur. L'utilisateur verrait une connexion « réussie » suivie d'un
  // rebond immédiat vers /connexion, sans la moindre explication.
  const entetes = new Headers()
  entetes.append('set-cookie', 'jobbot_session=abc.def.ghi; Path=/; HttpOnly; SameSite=lax')
  const session = lireCookieSession(entetes)

  assert.equal(session?.valeur, 'abc.def.ghi')
  assert.equal(session?.maxAge, undefined)

  const attributs = attributsCookieSession(session?.maxAge)
  assert.ok(!('maxAge' in attributs), 'la clé maxAge doit être absente, pas posée à 0')
})

test('un Max-Age nul ou négatif est traité comme absent', () => {
  for (const brut of ['Max-Age=0', 'Max-Age=-1']) {
    const entetes = new Headers()
    entetes.append('set-cookie', `jobbot_session=x; ${brut}; Path=/`)
    assert.equal(lireCookieSession(entetes)?.maxAge, undefined, `non traité : ${brut}`)
  }
})

test('listeTropLongue nomme la liste qui déborde, et de combien', () => {
  // Le cas réel : un CV qui donne 60 compétences. Sans ce contrôle, l'API
  // répond un 422 de pydantic sans clé `erreur` et l'écran n'a rien à dire.
  const donnees = {
    nom_complet: 'Awa Diop',
    titre: null,
    competences: Array.from({ length: 60 }, (_, i) => `competence ${i}`),
    langues: ['français'],
    secteurs_vises: [],
    mobilite: null,
    type_contrat: null,
  }
  assert.deepEqual(listeTropLongue(donnees), {
    champ: 'competences',
    saisi: 60,
    limite: LIMITES_LISTES.competences,
  })
})

test('listeTropLongue laisse passer une liste pile à la limite', () => {
  const donnees = {
    nom_complet: null,
    titre: null,
    competences: Array.from({ length: LIMITES_LISTES.competences }, (_, i) => `c${i}`),
    langues: Array.from({ length: LIMITES_LISTES.langues }, (_, i) => `l${i}`),
    secteurs_vises: Array.from({ length: LIMITES_LISTES.secteurs_vises }, (_, i) => `s${i}`),
    mobilite: null,
    type_contrat: null,
  }
  assert.equal(listeTropLongue(donnees), null)
})

test('le message de dépassement nomme la liste, la limite et le nombre à retirer', () => {
  const message = texteTropDeValeurs('competences', 60, 50)
  assert.match(message, /compétences/)
  assert.match(message, /50/)
  assert.match(message, /10/)
  // Jamais le nom de colonne : ce n'est pas du français (§11).
  assert.ok(!message.includes('competences'))
})

test('un brouillon fait l’aller-retour par le cookie sans rien perdre', () => {
  const donnees = {
    nom_complet: 'Awa Diop',
    titre: 'Comptable, à Dakar & ailleurs',
    competences: ['SAGE', 'Excel'],
    langues: ['français', 'wolof'],
    secteurs_vises: ['Comptabilité et finance'],
    mobilite: 'Dakar',
    type_contrat: 'CDI',
  }
  const valeur = serialiserBrouillon(donnees)
  assert.ok(valeur)
  assert.deepEqual(lireBrouillon(valeur), donnees)
})

test('un champ vidé par l’utilisateur reste vide au retour', () => {
  // La saisie fait foi EN BLOC : sans cela, effacer un champ serait annulé par
  // la valeur enregistrée, et l'utilisateur ne pourrait jamais rien supprimer.
  const valeur = serialiserBrouillon({
    nom_complet: null,
    titre: null,
    competences: [],
    langues: [],
    secteurs_vises: [],
    mobilite: null,
    type_contrat: null,
  })
  assert.deepEqual(lireBrouillon(valeur!)?.nom_complet, null)
})

test('un brouillon trop gros pour un cookie est abandonné, jamais tronqué', () => {
  // Un cookie de plus de 4 Ko est jeté par le navigateur SANS erreur : poser
  // un brouillon ingérable ferait perdre la saisie sans que personne ne le voie.
  const enorme = {
    nom_complet: null,
    titre: null,
    competences: Array.from({ length: 50 }, () => 'x'.repeat(200)),
    langues: [],
    secteurs_vises: [],
    mobilite: null,
    type_contrat: null,
  }
  assert.equal(serialiserBrouillon(enorme), null)
})

test('un cookie de brouillon trafiqué ne casse pas l’écran', () => {
  assert.equal(lireBrouillon('pas du base64url valide !!'), null)
  assert.equal(lireBrouillon(undefined), null)
  // Un JSON valide mais de mauvaise forme donne des listes vides, pas un plantage.
  const tordu = Buffer.from('{"competences": 3}', 'utf8').toString('base64url')
  assert.deepEqual(lireBrouillon(tordu)?.competences, [])
})

test('un brouillon sérialisé ne contient que des caractères sûrs pour un cookie', () => {
  // `cookies().set` encode ce qu'on lui donne, `cookies().get` ne décode RIEN :
  // tout caractère qu'`encodeURIComponent` toucherait reviendrait illisible, et
  // le brouillon ne se rappliquerait jamais. Défaut constaté en vrai.
  const valeur = serialiserBrouillon({
    nom_complet: 'Awa Diop, « comptable » & fière de l’être',
    titre: null,
    competences: ['SAGE/Excel', 'français + wolof'],
    langues: [],
    secteurs_vises: [],
    mobilite: null,
    type_contrat: null,
  })
  assert.ok(valeur)
  assert.equal(encodeURIComponent(valeur), valeur)
  assert.equal(lireBrouillon(valeur)?.nom_complet, 'Awa Diop, « comptable » & fière de l’être')
})

/** Des libellés de compétences RÉELS, en français, tels qu'un CV de comptable
 *  sénégalais en donne. Moyenne : 37 signes. Les anciens tests employaient
 *  `c0`, `Comp00` — des valeurs qui n'approchent jamais la borne du cookie, et
 *  qui ne pouvaient donc pas voir la perte silencieuse. */
const COMPETENCES_REELLES = [
  'Gestion administrative et financière',
  'Comptabilité générale et analytique',
  'Élaboration des états financiers annuels',
  'Déclarations fiscales et sociales',
  'Suivi budgétaire et contrôle de gestion',
  'Rapprochements bancaires mensuels',
  'Gestion de la paie et des bulletins',
  'Négociation avec les fournisseurs étrangers',
  'Tenue des livres comptables de la filiale',
  'Préparation et suivi des audits annuels',
  'Recouvrement des créances clients',
  'Gestion des immobilisations corporelles',
]

function profilDeSoixanteCompetences(nom: string) {
  return {
    nom_complet: nom,
    titre: 'Chef comptable',
    competences: Array.from(
      { length: 60 },
      (_, i) => COMPETENCES_REELLES[i % COMPETENCES_REELLES.length]!,
    ),
    langues: ['français', 'wolof', 'anglais'],
    secteurs_vises: ['Comptabilité et finance'],
    mobilite: 'Dakar',
    type_contrat: 'CDI',
  }
}

test('la correction d’un champ simple survit à 60 compétences réalistes', () => {
  // Le scénario EXACT que le brouillon devait couvrir : l'utilisateur corrige
  // son nom, soumet, et reçoit « vous avez 60 compétences, retirez-en 10 ».
  // Avec le profil entier dans le cookie, le brouillon franchissait la borne,
  // était jeté, et le nom d'avant revenait — sans un mot.
  const enregistre = profilDeSoixanteCompetences('Awa Diop')
  const saisi = profilDeSoixanteCompetences('Awa Diop Ndiaye')

  // D'abord : ces valeurs franchissent BIEN le seuil. Un test qui reste sous la
  // borne ne prouverait rien.
  assert.equal(
    serialiserBrouillon(saisi),
    null,
    'valeurs de test trop courtes : elles ne reproduisent pas le défaut',
  )

  // Ensuite : réduit à ce qui a changé, le brouillon tient — et tout revient.
  const valeur = serialiserBrouillon(differenceBrouillon(saisi, enregistre))
  assert.ok(valeur, 'la correction doit pouvoir être conservée')
  assert.ok(valeur.length < 200, `brouillon inutilement gros : ${valeur.length} octets`)
  assert.deepEqual(appliquerBrouillon(lireBrouillon(valeur), enregistre), saisi)
})

test('un champ vidé exprès reste vide, même quand le reste ne bouge pas', () => {
  // La règle que l'ancien « le brouillon fait foi en bloc » protégeait : une
  // suppression volontaire ne doit jamais être annulée par la valeur
  // enregistrée. Un champ vidé DIFFÈRE de la référence, donc il entre dans le
  // brouillon — et le `null` l'emporte au recollage.
  const enregistre = profilDeSoixanteCompetences('Awa Diop')
  const saisi = { ...profilDeSoixanteCompetences('Awa Diop'), titre: null, langues: [] }

  const diff = differenceBrouillon(saisi, enregistre)
  assert.deepEqual(Object.keys(diff).sort(), ['langues', 'titre'])
  const valeur = serialiserBrouillon(diff)
  assert.ok(valeur)
  const relu = appliquerBrouillon(lireBrouillon(valeur), enregistre)
  assert.equal(relu.titre, null)
  assert.deepEqual(relu.langues, [])
  assert.deepEqual(relu.competences, enregistre.competences)
})

test('sans profil de référence, le brouillon porte tout', () => {
  // Repli quand l'API ne répond pas pendant l'aller-retour d'erreur : on ne
  // peut rien recoller, donc on garde tout. La borne reprend ses droits, et
  // c'est alors à l'appelant de dire que la saisie n'a pas été conservée.
  const saisi = profilDeSoixanteCompetences('Awa Diop Ndiaye')
  assert.deepEqual(differenceBrouillon(saisi, null), saisi)
  assert.equal(serialiserBrouillon(differenceBrouillon(saisi, null)), null)
})

test('un brouillon absent laisse le profil enregistré intact', () => {
  const enregistre = profilDeSoixanteCompetences('Awa Diop')
  assert.deepEqual(appliquerBrouillon(null, enregistre), enregistre)
})

test('brouillonDepuisStructured ignore ce qui n’est pas du bon type', () => {
  // `structured` vient de l'API, donc d'un LLM : rien n'y garantit les types.
  const vu = brouillonDepuisStructured({
    nom_complet: 'Awa Diop',
    titre: 42,
    competences: ['Excel', 7, null],
    langues: 'français',
  })
  assert.equal(vu.nom_complet, 'Awa Diop')
  assert.equal(vu.titre, null)
  assert.deepEqual(vu.competences, ['Excel'])
  assert.deepEqual(vu.langues, [])
})

test("le cookie de brouillon ne remonte que sur l'écran qui s'en sert", () => {
  // Sur `path: '/'`, un cookie de 3,5 Ko qui vit 15 minutes repartait avec
  // TOUTES les requêtes, les fragments `/_next/` compris : de l'ordre de 25 Ko
  // d'émission par chargement de page, sur une data comptée (§11). Invisible
  // pour `mesure-poids.mjs`, qui ne compte que la descente.
  assert.equal(attributsCookieBrouillon().path, '/profil')
  // Et l'effacement vise le MÊME chemin : un navigateur n'efface un cookie que
  // si le chemin correspond. Sans cela, le brouillon d'un essai précédent se
  // rappliquerait indéfiniment sur l'écran.
  const effacement = effacementCookieBrouillon()
  assert.equal(effacement.path, attributsCookieBrouillon().path)
  assert.equal(effacement.name, COOKIE_BROUILLON)
})
