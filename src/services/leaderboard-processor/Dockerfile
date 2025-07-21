
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci --only=production

# Copy source code
COPY . .

# Build the TypeScript
RUN npm run build

EXPOSE 8080

CMD ["npm", "start"]
