# Pinned deps via package-lock. Unlike the npx-at-runtime MCP servers in
# docker-compose.yml, this image resolves everything at build time, so it does
# not need npm reachable to start.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
USER node
EXPOSE 8000
CMD ["node", "dist/server.js"]
