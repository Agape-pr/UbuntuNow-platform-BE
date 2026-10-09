FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production

# Copy package files from the api-gateway directory
COPY api-gateway/package*.json ./
RUN npm ci --omit=dev

# Copy the rest of the api-gateway code
COPY api-gateway/ ./

EXPOSE 8000

CMD ["node", "index.js"]
