FROM node:18-alpine

WORKDIR /app

# Copy package files from the api-gateway directory
COPY api-gateway/package*.json ./
RUN npm install --production

# Copy the rest of the api-gateway code
COPY api-gateway/ ./

EXPOSE 8000

CMD ["node", "index.js"]
