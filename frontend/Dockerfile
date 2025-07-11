# Build stage
FROM node:18-alpine as builder

WORKDIR /app

# Copie des fichiers de dépendances
COPY package*.json ./
RUN npm ci --only=production

# Copie du code source et build
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copie de la configuration nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Copie des fichiers buildés
COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
