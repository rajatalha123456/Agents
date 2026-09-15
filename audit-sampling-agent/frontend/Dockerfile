# Multi-stage: build the Vite static bundle, serve it with nginx as a
# non-root user. VITE_API_BASE_URL is baked in at build time (Vite env
# vars are compile-time, not runtime) -- pass it as a build arg.
FROM node:20-slim AS builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine AS runtime

RUN adduser -D -u 1000 app \
    && rm -rf /usr/share/nginx/html/*

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx needs to write to these at runtime even when running as non-root.
RUN touch /var/run/nginx.pid \
    && chown -R app:app /var/cache/nginx /var/run/nginx.pid /usr/share/nginx/html /etc/nginx/conf.d

USER app
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
