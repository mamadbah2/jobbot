import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  ipCliente,
  lireCookieSession,
  attributsCookieSession,
  listeTropLongue,
  lireBrouillon,
  serialiserBrouillon,
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
