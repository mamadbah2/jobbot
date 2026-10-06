import type { NextConfig } from 'next'

const config: NextConfig = {
  // L'image de production ne doit pas porter les node_modules de build.
  output: 'standalone',
  // Aucune image distante, aucun optimiseur : la cible est un Android
  // d'entrée de gamme sur data comptée (CLAUDE.md §11).
  images: { unoptimized: true },
  poweredByHeader: false,
  // Les Server Actions plafonnent à 1 Mo par défaut, en dessous de beaucoup de
  // PDF et de toutes les photos. Constante FIGÉE, strictement supérieure à
  // CV_TAILLE_MAX_MO (5) + MARGE_MULTIPART (64 Ko) côté API : tout fichier
  // entre 5 et 8 Mo atteint ainsi l'API, qui répond `cv_trop_gros` avec son
  // message français. Plus bas, Next couperait lui-même et l'utilisateur
  // verrait l'écran d'erreur générique, en anglais (§11) — et une photo de CV
  // prise au téléphone pèse souvent 4 à 10 Mo.
  // Au-delà de 8 Mo on retombe sur l'écran de Next : cas rare, assumé.
  // Pas d'interpolation de variable d'environnement : cette valeur est figée
  // au BUILD (`standalone`), une variable d'exécution n'aurait aucun effet.
  experimental: {
    serverActions: { bodySizeLimit: '8mb' },
  },
}

export default config
