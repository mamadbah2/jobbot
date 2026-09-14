# Build multi-étapes : l'image finale ne porte pas les node_modules de build.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
# Sans cette ligne, le serveur n'écoute PAS sur 0.0.0.0, par accident : le
# `server.js` de `output: "standalone"` lit `process.env.HOSTNAME || '0.0.0.0'`,
# et Docker renseigne HOSTNAME avec l'ID du conteneur. Le service n'écoutait
# donc que sur l'IP du conteneur, `wget http://127.0.0.1:3000` était refusé
# depuis l'intérieur, et c'est pourquoi `web` était le seul service sans
# healthcheck. Le Dockerfile officiel de Next porte la même ligne, pour la
# même raison.
ENV HOSTNAME="0.0.0.0"
# `output: "standalone"` produit un serveur autonome et sa liste minimale de
# modules : l'image ne porte ni les sources, ni les dépendances de build.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
