FROM node:22-bookworm-slim AS build
RUN corepack enable && corepack prepare pnpm@11 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages ./packages
COPY apps/client ./apps/client
COPY apps/admin ./apps/admin
COPY deploy/cloud/generated/client.toml ./apps/client/client.toml
RUN pnpm install --frozen-lockfile \
    && pnpm --filter @hymio/app build \
    && pnpm --filter @hymio/admin build
FROM caddy:2.10.2-alpine
COPY --from=build /app/apps/client/dist /srv
COPY --from=build /app/apps/admin/dist /srv/admin
