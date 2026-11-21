# Multi-stage: build with full deps, run with the standalone bundle only.
# Runs as a non-root user, and is never given a docker socket — that is the
# point of the whole design (see README.md).

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# /app/registry is a BIND MOUNT from the novak stack repo — deliberately not
# baked into the image, because the registry belongs to the stack, not to this
# app. Create the mount point so the container still starts when nothing is
# mounted; the app then reports the registry as unavailable rather than dying.
RUN mkdir -p /app/registry && chown nextjs:nodejs /app/registry
USER nextjs
EXPOSE 3002
ENV PORT=3002 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
