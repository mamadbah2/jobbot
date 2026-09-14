import type { Metadata } from 'next'
import './styles.css'

export const metadata: Metadata = {
  title: 'JobBot',
  description: "Les offres d'emploi du Sénégal, réunies au même endroit.",
}

export default function RacineLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  )
}
