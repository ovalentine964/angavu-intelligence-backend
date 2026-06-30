# Msaidizi OpenWA — WhatsApp Bot Service

Self-hosted WhatsApp Web API using the [Baileys](https://github.com/WhiskeySockets/Baileys) library.

## Architecture

```
WhatsApp Cloud ←→ Baileys (WhatsApp Web) ←→ OpenWA Express ←→ Msaidizi Backend
```

The OpenWA service acts as a bridge between WhatsApp and the Msaidizi backend API. It:

1. Connects to WhatsApp Web using Baileys (no official Business API needed)
2. Receives incoming messages via WebSocket
3. Forwards messages to the Msaidizi backend API for processing
4. Sends responses back to users via WhatsApp

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Start the service

```bash
npm start
```

### 4. Authenticate

On first run, a QR code will appear in the terminal. Scan it with WhatsApp on your phone:

1. Open WhatsApp on your phone
2. Go to Settings → Linked Devices
3. Scan the QR code

The authentication state is persisted in `./data/auth/` so you don't need to scan again on restart.

## API Endpoints

### POST /send-message
Send a WhatsApp message.
```json
{
  "to": "254712345678",
  "message": "Biashara yako leo: KES 4,500"
}
```

### POST /send-media
Send media (image, document, audio).
```json
{
  "to": "254712345678",
  "type": "image",
  "url": "https://example.com/chart.png",
  "caption": "Ripoti ya wiki"
}
```

### GET /status
Check connection status.

### GET /health
Health check.

## Features

- **Daily Reports**: Automatically sends business reports at 7 PM EAT
- **Message Routing**: Forwards messages to Msaidizi backend for processing
- **Auto-Reconnection**: Reconnects automatically on disconnect
- **QR Authentication**: Scan once, persists across restarts
- **Swahili Templates**: All messages support Swahili, English, and Sheng

## Docker

```bash
docker build -t msaidizi-openwa .
docker run -p 3000:3000 msaidizi-openwa
```

## Important Notes

- **Phone Number**: Use a dedicated business number, not your personal WhatsApp
- **Ban Risk**: WhatsApp may ban numbers used for automation. Mitigate by:
  - Not sending unsolicited messages
  - Rate-limiting outbound messages
  - Only responding to incoming messages
- **Official API**: Consider upgrading to WhatsApp Business API when revenue justifies cost

## License

Proprietary — Msaidizi / Biashara AI
