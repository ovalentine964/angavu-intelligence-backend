# Msaidizi API Documentation

## Base URL
```
https://api.msaidizi.app
```

## Authentication
Protected endpoints require JWT token in Authorization header:
```
Authorization: Bearer <token>
```

## Endpoints

### WhatsApp Connection

#### POST /api/v1/whatsapp/connect

Initiate WhatsApp connection during onboarding.

**Request Body:**
```json
{
    "phone": "+254712345678",
    "user_id": "user-uuid",
    "name": "Valentine",
    "assistant_name": "Simba",
    "language": "sw",
    "report_time": "evening"
}
```

**Response (200 OK):**
```json
{
    "status": "sent",
    "verification_id": "verification-uuid",
    "message": "Ujumbe wa WhatsApp umetumwa. Angalia WhatsApp yako."
}
```

**Error Responses:**
- `400 Bad Request` - Missing or invalid fields
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

**Error Codes:**
- `MISSING_FIELDS` - Required fields missing
- `INVALID_PHONE` - Invalid phone format
- `NUMBER_NOT_ON_WHATSAPP` - Number not registered on WhatsApp
- `RATE_LIMIT` - Too many requests
- `SEND_FAILED` - Failed to send message
- `INTERNAL_ERROR` - Internal server error

---

#### POST /api/v1/whatsapp/verify

Confirm WhatsApp connection.

**Request Body:**
```json
{
    "verification_id": "verification-uuid",
    "code": "1234"
}
```

**Response (200 OK):**
```json
{
    "status": "connected",
    "whatsapp_id": "whatsapp-uuid",
    "message": "WhatsApp imeunganishwa!"
}
```

**Status Values:**
- `connected` - Successfully connected
- `pending` - Still waiting for confirmation
- `expired` - Verification expired
- `error` - Error occurred

---

#### GET /api/v1/whatsapp/verify/:verificationId/status

Poll verification status.

**Response (200 OK):**
```json
{
    "status": "pending",
    "message": "Bado nasubiri uthibitisho..."
}
```

---

#### GET /api/v1/whatsapp/connection/:userId

Get current WhatsApp connection state.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
    "user_id": "user-uuid",
    "phone": "+254712345678",
    "connected": true,
    "connected_at": "2024-01-15T10:30:00Z",
    "assistant_name": "Simba",
    "language": "sw",
    "report_time": "evening",
    "last_report_sent": "2024-01-15T18:00:00Z"
}
```

---

#### POST /api/v1/whatsapp/disconnect/:userId

Disconnect WhatsApp from user account.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
    "status": "disconnected",
    "message": "WhatsApp imeondolewa."
}
```

---

### Reports

#### POST /api/v1/whatsapp/send-report

Trigger a report send via WhatsApp.

**Headers:**
```
Authorization: Bearer <token>
```

**Request Body:**
```json
{
    "user_id": "user-uuid",
    "report_type": "daily",
    "date": "2024-01-15"
}
```

**Response (200 OK):**
```json
{
    "status": "sent",
    "message_id": "message-uuid",
    "message": "Ripoti imetumwa kupitia WhatsApp."
}
```

**Report Types:**
- `daily` - Daily sales report
- `weekly` - Weekly summary report

---

### Health Check

#### GET /health

Check API health status.

**Response (200 OK):**
```json
{
    "status": "healthy",
    "timestamp": "2024-01-15T10:30:00Z",
    "uptime": 3600
}
```

---

## WhatsApp Commands

Users can send these commands to the Msaidizi WhatsApp number:

| Command | Description |
|---------|-------------|
| `ripoti` / `report` | Get today's report |
| `mauzo` / `sales` | Get sales summary |
| `faida` / `profit` | Get profit summary |
| `wiki` / `weekly` | Get weekly report |
| `msaada` / `help` | Show command list |
| `shiriki` / `share` | Get share link |
| `simama` / `stop` | Unsubscribe from reports |
| `anza` / `start` | Resubscribe to reports |
| `kiswahili` | Switch to Swahili |
| `sheng` | Switch to Sheng |
| `english` | Switch to English |
| `hali` / `status` | Show connection status |

---

## Report Templates

### Daily Report (Swahili)
```
📊 *Ripoti ya Leo — Simba*

👤 Valentine, hii leo:
💰 Mauzo: KSh 3,200
📦 Bidhaa zilizouzwa: 12
📈 Faida: KSh 800
💡 *Kidokezo: Mandazi yanaongezeka soko leo. Ongeza stock!*

🔗 Pakua Msaidizi: [link]
📤 Shiriki na rafiki: [link]
```

### Weekly Report (Swahili)
```
📊 *Ripoti ya Wiki — Simba*

👤 Valentine, wiki hii:
💰 Mauzo jumla: KSh 18,500
📈 Faida jumla: KSh 4,200
📊 Mauzo ya juu: Jumatatu (KSh 4,100)
📉 Mauzo ya chini: Jumamosi (KSh 1,800)
💡 *Kidokezo: Wiki ijayo, fungua mapema Jumatatu — ndio soko yako bora!*
```

### Share Message (Swahili)
```
🎉 Simba — Msaidizi wa Biashara!

Ninatumia Simba kurekodi mauzo yangu kwa sauti. Inafanya kazi bila internet!

Pakua bure: [GitHub Releases link]
Jiunge na WhatsApp: [group link]
```

---

## Error Handling

All errors follow this format:
```json
{
    "status": "error",
    "error_code": "ERROR_CODE",
    "message": "Human-readable error message"
}
```

### Common Error Codes

| Code | Description |
|------|-------------|
| `MISSING_FIELDS` | Required fields missing |
| `INVALID_PHONE` | Invalid phone format |
| `NUMBER_NOT_ON_WHATSAPP` | Number not registered on WhatsApp |
| `RATE_LIMIT` | Too many requests |
| `SEND_FAILED` | Failed to send message |
| `VERIFICATION_EXPIRED` | Verification expired |
| `INTERNAL_ERROR` | Internal server error |
| `UNAUTHORIZED` | Missing or invalid token |
| `FORBIDDEN` | Insufficient permissions |

---

## Rate Limiting

- **Global:** 100 requests per 15 minutes per IP
- **Connect endpoint:** 5 requests per minute per IP
- **Verify endpoint:** 10 requests per minute per IP
- **WhatsApp commands:** 20 messages per minute per user

---

## Webhooks

### Incoming Message Webhook

When a WhatsApp message is received, OpenWA sends a POST request to the configured webhook URL:

```json
{
    "event": "message",
    "data": {
        "id": "message-id",
        "from": "254712345678@c.us",
        "body": "ripoti",
        "timestamp": 1705312200
    }
}
```

### Delivery Receipt Webhook

When a message is delivered or read:

```json
{
    "event": "receipt",
    "data": {
        "message_id": "message-id",
        "to": "254712345678@c.us",
        "status": "delivered",
        "timestamp": 1705312200
    }
}
```
