FROM node:26-slim AS build

WORKDIR /app

RUN npm install --global pnpm@10.26.2 \
    && npm cache clean --force

COPY frontend/package.json frontend/pnpm-lock.yaml /app/frontend/
WORKDIR /app/frontend
RUN pnpm install --frozen-lockfile

COPY frontend /app/frontend

ARG NEXT_PUBLIC_DATA_MODE=api
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_DIALOG_TRANSPORT=websocket
ARG NEXT_PUBLIC_API_TIMEOUT_MS=15000
ENV NEXT_PUBLIC_DATA_MODE=${NEXT_PUBLIC_DATA_MODE} \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_DIALOG_TRANSPORT=${NEXT_PUBLIC_DIALOG_TRANSPORT} \
    NEXT_PUBLIC_API_TIMEOUT_MS=${NEXT_PUBLIC_API_TIMEOUT_MS}

RUN pnpm build

FROM node:26-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin nextjs

COPY --from=build --chown=nextjs:nextjs /app/frontend/.next/standalone /app
COPY --from=build --chown=nextjs:nextjs /app/frontend/.next/static /app/.next/static
COPY --from=build --chown=nextjs:nextjs /app/frontend/public /app/public

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
