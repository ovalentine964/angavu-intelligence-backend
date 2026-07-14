FROM node:20-alpine

WORKDIR /app

# Install wget and curl for health checks
RUN apk add --no-cache wget curl

COPY package.json ./
RUN npm install --production

COPY . .

RUN mkdir -p /app/data/auth

# Health check script — quick HTTP liveness check
# The docker-compose start_period (5 min) handles the QR scan timeout
RUN printf '#!/bin/sh\nwget -q --spider http://localhost:3000/health 2>/dev/null\n' > /app/healthcheck.sh && chmod +x /app/healthcheck.sh

EXPOSE 3000

CMD ["node", "index.js"]
