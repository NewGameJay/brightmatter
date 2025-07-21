
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm install --only=production

# Copy source code
COPY . .

EXPOSE 8080

CMD ["node", "index.js"]
