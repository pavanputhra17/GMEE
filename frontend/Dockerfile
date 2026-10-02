# Production image: build the SPA, then serve it statically with nginx.
# (The previous image ran `npm run dev` — Vite's dev server with HMR — fine
# for a local demo, but not what "production" means.)
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# Baked at build time. Default = same-origin /api/v1, which nginx proxies to
# the backend (see nginx.conf), so runtime CORS config is unnecessary.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

