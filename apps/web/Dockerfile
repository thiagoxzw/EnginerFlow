# Frontend EngiFlow (Next.js). Build de produção servido pelo `next start`.
FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1 \
    ENGIFLOW_API_URL=http://api:8000

RUN corepack enable && corepack prepare pnpm@10.34.9 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

RUN addgroup -S engiflow && adduser -S -G engiflow engiflow
USER engiflow

EXPOSE 3000
CMD ["pnpm", "start", "--hostname", "0.0.0.0", "--port", "3000"]
