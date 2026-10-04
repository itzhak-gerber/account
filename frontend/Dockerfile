# syntax=docker/dockerfile:1
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Local development: Vite dev server with hot reload.
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]

FROM deps AS build
COPY . .
RUN npm run build

# Static files only; in Azure the same dist/ goes to Static Web Apps.
FROM nginxinc/nginx-unprivileged:1.29-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
