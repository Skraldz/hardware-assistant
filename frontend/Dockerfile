FROM node:20-slim

WORKDIR /app

# Copy the lockfile too, and use `npm ci`, so the image installs exactly
# what was tested instead of letting npm re-resolve semver ranges.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 4173

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["npm", "run", "preview"]
