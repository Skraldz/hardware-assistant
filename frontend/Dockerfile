FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# Baked into the built JS at build time (Vite's import.meta.env.VITE_*
# substitution happens during `npm run build`, not at container runtime) —
# see docker-compose.yml's `args`. Defaults to the backend's own default port.
ARG VITE_API_PORT=8000
ENV VITE_API_PORT=$VITE_API_PORT
RUN npm run build

EXPOSE 4173

CMD ["npm", "run", "preview"]
