# Keigan web image: static React build served by unprivileged nginx, proxying /api to the backend namespace.
# Build from the repository root:  docker build -f deploy/docker/frontend.Dockerfile -t keigan-web:0.1.0 .
FROM node:22-alpine AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
# BACKEND_URL is substituted into the template at container start (nginx envsubst templates).
ENV BACKEND_URL=http://keigan-api.keigan-backend.svc.cluster.local:8080
COPY deploy/docker/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 8080
