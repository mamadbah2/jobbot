import type { NextConfig } from 'next'

const config: NextConfig = {
  // L'image de production ne doit pas porter les node_modules de build.
  output: 'standalone',
  // Aucune image distante, aucun optimiseur : la cible est un Android
  // d'entrée de gamme sur data comptée (CLAUDE.md §11).
  images: { unoptimized: true },
  poweredByHeader: false,
}

export default config
