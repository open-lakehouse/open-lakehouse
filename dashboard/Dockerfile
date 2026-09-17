# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Containerized Lakehouse Platform Contributors

FROM node:22-alpine AS deps
WORKDIR /app
# Copy the lockfile too and use `npm ci` for a reproducible install pinned to
# package-lock.json (resolves to the public registry; a proxy passed via
# NPM_REGISTRY is remapped onto those npmjs URLs at fetch time).
COPY package.json package-lock.json ./
ARG NPM_REGISTRY=
ARG NPM_STRICT_SSL=true
RUN npm config set strict-ssl ${NPM_STRICT_SSL} && \
    if [ -n "${NPM_REGISTRY}" ]; then npm config set registry "${NPM_REGISTRY}"; fi && \
    npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
