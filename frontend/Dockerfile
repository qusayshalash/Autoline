# The web server: the built interface, served by Caddy, which also forwards /api to the
# backend and obtains the HTTPS certificate on its own. Started by
# deploy/docker-compose.yml, which mounts deploy/Caddyfile into it.

FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /src/dist /srv
