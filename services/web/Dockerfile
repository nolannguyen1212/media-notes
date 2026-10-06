# syntax=docker/dockerfile:1

FROM node:22-alpine AS base
RUN npm install -g pnpm@10
WORKDIR /src/services/web

FROM base AS deps
COPY services/web/package.json services/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS builder
COPY services/hermes/internal/graphql/schema.graphqls /src/services/hermes/internal/graphql/schema.graphqls
COPY services/web/ ./
ARG VITE_HERMES_URL
ENV VITE_HERMES_URL=${VITE_HERMES_URL}
RUN pnpm codegen
RUN pnpm build

FROM nginx:1.27-alpine AS runner
COPY --from=builder /src/services/web/build/client /usr/share/nginx/html
COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000
