FROM node:20-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Dedicated Node test target; nginx production images intentionally have no npm.
FROM dependencies AS test
COPY . .
CMD ["npm", "run", "test"]

FROM test AS build
# Build-time setting, not a secret. The Docker deployment uses a same-origin API.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:stable-alpine AS production
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
