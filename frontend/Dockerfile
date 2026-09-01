FROM node:22-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# Официальный непривилегированный образ nginx (nginx team, тот же движок,
# что и nginx:1.30-alpine) — уже сконфигурирован под запуск без root:
# слушает 8080 вместо 80, pid/temp-пути в /tmp вместо /var/run (там нет
# прав у некорневого пользователя). См. https://github.com/nginxinc/docker-nginx-unprivileged
FROM nginxinc/nginx-unprivileged:1.30-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
