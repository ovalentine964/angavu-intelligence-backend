# Msaidizi Deployment Guide

## Prerequisites

- Docker and Docker Compose
- Domain name (for production)
- WhatsApp phone number for Msaidizi bot
- SSL certificate (for production)

## Quick Start (Development)

### 1. Clone and Configure

```bash
cd msaidizi-backend
cp .env.example .env
```

Edit `.env` with your configuration:
```bash
# Generate a secure JWT secret
JWT_SECRET=$(openssl rand -base64 32)

# Set OpenWA API key
OPENWA_API_KEY=$(openssl rand -base64 16)

# Set database password
DB_PASSWORD=$(openssl rand -base64 16)
```

### 2. Start Services

```bash
docker-compose up -d
```

This starts:
- Backend API (port 3000)
- OpenWA gateway (port 8080)
- PostgreSQL database (port 5432)
- Redis cache (port 6379)
- Nginx reverse proxy (port 80)

### 3. Initialize OpenWA

```bash
# Get QR code for WhatsApp Web
curl http://localhost:8080/session/msaidizi/qr

# Scan QR code with WhatsApp on your phone
# Open WhatsApp → Settings → Linked Devices → Link a Device
```

### 4. Verify Setup

```bash
# Check health
curl http://localhost:3000/health

# Check OpenWA status
curl http://localhost:8080/session/msaidizi/status
```

## Production Deployment

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose -y

# Create deployment directory
sudo mkdir -p /opt/msaidizi
sudo chown $USER:$USER /opt/msaidizi
```

### 2. Configure Environment

```bash
cd /opt/msaidizi

# Clone repository
git clone <repository-url> .

# Create production .env
cat > .env << EOF
NODE_ENV=production
PORT=3000
JWT_SECRET=$(openssl rand -base64 32)
OPENWA_API_KEY=$(openssl rand -base64 16)
OPENWA_SESSION_ID=msaidizi
DB_PASSWORD=$(openssl rand -base64 16)
ALLOWED_ORIGINS=https://msaidizi.app,https://api.msaidizi.app
LOG_LEVEL=info
EOF
```

### 3. SSL Certificate

```bash
# Install Certbot
sudo apt install certbot -y

# Get certificate
sudo certbot certonly --standalone -d api.msaidizi.app

# Copy certificates
sudo mkdir -p nginx/ssl
sudo cp /etc/letsencrypt/live/api.msaidizi.app/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/api.msaidizi.app/privkey.pem nginx/ssl/
sudo chown -R $USER:$USER nginx/ssl/
```

### 4. Update Nginx Configuration

Edit `nginx/nginx.conf` to enable HTTPS:
```nginx
server {
    listen 443 ssl http2;
    server_name api.msaidizi.app;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... rest of configuration
}
```

### 5. Deploy

```bash
# Build and start
docker-compose -f docker-compose.yml up -d --build

# Check logs
docker-compose logs -f

# Verify
curl https://api.msaidizi.app/health
```

### 6. Auto-renew SSL

```bash
# Create renewal script
cat > /opt/msaidizi/renew-ssl.sh << 'EOF'
#!/bin/bash
certbot renew
cp /etc/letsencrypt/live/api.msaidizi.app/fullchain.pem /opt/msaidizi/nginx/ssl/
cp /etc/letsencrypt/live/api.msaidizi.app/privkey.pem /opt/msaidizi/nginx/ssl/
docker-compose restart nginx
EOF

chmod +x /opt/msaidizi/renew-ssl.sh

# Add to crontab
echo "0 0 1 * * /opt/msaidizi/renew-ssl.sh" | crontab -
```

## Monitoring

### Health Checks

```bash
# Backend health
curl https://api.msaidizi.app/health

# OpenWA status
curl https://api.msaidizi.app/api/v1/whatsapp/status

# Database connection
docker-compose exec postgres pg_isready
```

### Logs

```bash
# All logs
docker-compose logs -f

# Backend logs only
docker-compose logs -f backend

# OpenWA logs only
docker-compose logs -f openwa

# PostgreSQL logs
docker-compose logs -f postgres
```

### Backup

```bash
# Backup database
docker-compose exec postgres pg_dump -U msaidizi msaidizi > backup_$(date +%Y%m%d).sql

# Backup OpenWA session
docker-compose exec openwa tar czf /tmp/session-backup.tar.gz /app/session-data
docker cp msaidizi-openwa:/tmp/session-backup.tar.gz ./backup/session_$(date +%Y%m%d).tar.gz
```

## Scaling

### Horizontal Scaling

```bash
# Scale backend instances
docker-compose up -d --scale backend=3

# Update Nginx upstream
# Edit nginx.conf to add more backend servers
```

### Database Scaling

```bash
# Add read replica
docker-compose -f docker-compose.yml -f docker-compose.replica.yml up -d
```

## Troubleshooting

### OpenWA Not Connecting

```bash
# Check OpenWA status
curl http://localhost:8080/session/msaidizi/status

# Restart OpenWA
docker-compose restart openwa

# Get new QR code
curl http://localhost:8080/session/msaidizi/qr
```

### Database Connection Issues

```bash
# Check PostgreSQL status
docker-compose exec postgres pg_isready

# Check database logs
docker-compose logs postgres

# Connect to database
docker-compose exec postgres psql -U msaidizi msaidizi
```

### High Memory Usage

```bash
# Check container resources
docker stats

# Restart services
docker-compose restart

# Limit memory in docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 512M
```

### Rate Limiting Issues

```bash
# Check Nginx logs
docker-compose logs nginx | grep "limiting"

# Adjust rate limits in nginx.conf
# Increase limit_req_zone rate
```

## Maintenance

### Update Dependencies

```bash
# Pull latest images
docker-compose pull

# Rebuild and restart
docker-compose up -d --build
```

### Clear Logs

```bash
# Clear old logs
find /opt/msaidizi/logs -name "*.log" -mtime +30 -delete

# Clear Docker logs
sudo truncate -s 0 /var/lib/docker/containers/*/\*-json.log
```

### Database Maintenance

```bash
# Vacuum database
docker-compose exec postgres vacuumdb -U msaidizi msaidizi

# Analyze tables
docker-compose exec postgres analyzedb -U msaidizi msaidizi
```

## Security Checklist

- [ ] Change default passwords
- [ ] Enable HTTPS
- [ ] Set up firewall (allow only 80, 443)
- [ ] Regular security updates
- [ ] Monitor logs for suspicious activity
- [ ] Backup database regularly
- [ ] Test disaster recovery
- [ ] Set up monitoring alerts
- [ ] Review rate limiting settings
- [ ] Audit API access logs
