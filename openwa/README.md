# Msaidizi OpenWA — WhatsApp Bot Service

Self-hosted WhatsApp Web API using the [Baileys](https://github.com/WhiskeySockets/Baileys) library.

## ⚠️ Ban Risk

This service uses **Baileys**, an unofficial WhatsApp library. Meta can ban the phone number at any time. See the main [README.md](../README.md#️-critical-risk-whatsapp-via-baileys-unofficial-library) for full risk documentation.

**Safety measures are built-in** — see [Safety Configuration](#safety-configuration) below.

## Architecture

```
WhatsApp Cloud ←→ Baileys (WhatsApp Web) ←→ OpenWA Express ←→ Msaidizi Backend
                                              ↑
                                    SafetyManager (queue, delays, ban detection)
```

The OpenWA service acts as a bridge between WhatsApp and the Msaidizi backend API. It:

1. Connects to WhatsApp Web using Baileys (no official Business API needed)
2. Receives incoming messages via WebSocket
3. Forwards messages to the Msaidizi backend API for processing
4. Sends responses back to users via WhatsApp
5. **Queues all outbound messages through SafetyManager** (human-like delays, rate limiting)

## Safety Configuration

All outbound messages go through the `WhatsAppSafetyManager` which enforces:

| Measure | Default | Env Var | Purpose |
|---------|---------|---------|---------|
| Max msg/sec | 10 | `WA_MAX_MSG_PER_SEC` | Per-second rate limit |
| Min delay | 2000ms | `WA_MIN_DELAY_MS` | Minimum gap between messages |
| Max delay | 8000ms | `WA_MAX_DELAY_MS` | Maximum gap (randomised) |
| Consecutive cap | 50 | `WA_MAX_CONSECUTIVE` | Messages before forced cooldown |
| Cooldown | 60s | `WA_COOLDOWN_MS` | Pause after consecutive limit |
| Max msg/min | 200 | `WA_MAX_MSG_PER_MIN` | Per-minute rate limit |
| Ban threshold | 5 | `WA_BAN_THRESHOLD` | Failures before ban declaration |
| Health check | 30s | `WA_HEALTH_INTERVAL_MS` | How often to check connection |
| Delivery timeout | 30s | `WA_DELIVERY_TIMEOUT_MS` | When to mark delivery as timed out |

### Human-Like Delays

Every message is delayed by a random interval (2-8 seconds by default) to mimic human typing behavior. This is the single most important ban-avoidance measure.

### Message Queue

Messages are queued FIFO with priority support. The queue:
- Never floods the connection (processes one at a time)
- Supports `high`, `normal`, `low` priority levels
- Automatically retries failed messages (up to 3 attempts)
- Drains gracefully when a ban is detected

### Ban Detection

The SafetyManager monitors consecutive send failures. If failures exceed the threshold (default: 5), it:
1. Marks the connection as banned
2. Rejects all queued messages
3. Notifies the backend via `POST /api/v1/channels/ban-detected`
4. Backend triggers automatic failover to Telegram

### Delivery Confirmation

Every sent message is tracked. Receipts from WhatsApp (delivered, read, played) are mapped back to the original message ID. Check delivery status via:

```
GET /delivery/:messageId
GET /delivery  (all tracked deliveries)
```

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
Send a WhatsApp message (queued through SafetyManager).
```json
{
  "to": "254712345678",
  "message": "Biashara yako leo: KES 4,500",
  "priority": "normal"
}
```

### POST /send-image
Send an image with optional caption.
```json
{
  "to": "254712345678",
  "image": "base64...",
  "caption": "Ripoti ya wiki"
}
```

### POST /send-voice
Send a voice note.

### POST /send-media
Send any media type.

### GET /status
Connection status.

### GET /health
Full health check with safety stats.

### GET /safety
Safety manager statistics and configuration.

### POST /safety/reset-ban
Reset ban state after confirming number is not banned.

### GET /delivery/:messageId
Check delivery status for a message.

### GET /delivery
List all tracked deliveries.

### GET /qr
Get QR code for authentication.

## Features

- **Safety Queue**: All messages queued with human-like delays
- **Ban Detection**: Auto-detects bans and notifies backend
- **Delivery Tracking**: Per-message receipt monitoring
- **Auto-Reconnection**: Reconnects automatically on disconnect
- **QR Authentication**: Scan once, persists across restarts
- **Voice Transcription**: Whisper STT for incoming voice notes
- **Swahili Support**: All messages support Swahili, English, and Sheng

## Docker

```bash
docker build -t msaidizi-openwa .
docker run -p 3000:3000 msaidizi-openwa
```

## Important Notes

- **Phone Number**: Use a dedicated business number, not your personal WhatsApp
- **Ban Risk**: Safety measures reduce but don't eliminate ban risk. See main README.
- **Official API**: Consider upgrading to WhatsApp Business API when revenue justifies cost

## License

Proprietary — Msaidizi / Angavu Intelligence
