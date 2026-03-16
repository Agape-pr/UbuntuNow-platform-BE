FROM node:18-alpine

WORKDIR /app

COPY api-gateway/package*.json ./
RUN npm install --production

COPY api-gateway .

EXPOSE 8000

CMD ["node", "index.js"]
