// Une ligne JSON par étape franchie (CLAUDE.md §11 : « compter et logger les
// abandons à chaque étape »).
//
// JAMAIS d'adresse email : le dépôt porte deux tests dont c'est l'objet
// (tests/test_logs_sans_pii.py). L'étape suffit à voir où le parcours perd
// des gens ; l'identité n'y ajoute rien et constituerait un fichier de
// données personnelles.

export function journaliser(etape: string, extra: Record<string, string | number> = {}): void {
  console.log(JSON.stringify({ evenement: 'parcours', etape, ...extra }))
}
