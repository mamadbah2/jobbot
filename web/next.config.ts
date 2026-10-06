import type { NextConfig } from 'next'

const config: NextConfig = {
  // L'image de production ne doit pas porter les node_modules de build.
  output: 'standalone',
  // Aucune image distante, aucun optimiseur : la cible est un Android
  // d'entrée de gamme sur data comptée (CLAUDE.md §11).
  images: { unoptimized: true },
  poweredByHeader: false,
  // Les Server Actions plafonnent à 1 Mo par défaut, en dessous de beaucoup de
  // PDF et de toutes les photos. Aligné sur CV_TAILLE_MAX_MO côté API : un
  // plafond relevé sans borne serait une porte ouverte.
  experimental: {
    serverActions: { bodySizeLimit: `${Number(process.env.CV_TAILLE_MAX_MO) || 5}mb` },
  },
}

export default config
