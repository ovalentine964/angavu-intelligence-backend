FROM node:20-alpine

WORKDIR /app

# Install wget for health checks
RUN apk add --no-cache wget

COPY package.json ./
RUN npm install --production

COPY . .

RUN mkdir -p /app/data/auth

EXPOSE 3000

CMD ["node", "index.js"]
