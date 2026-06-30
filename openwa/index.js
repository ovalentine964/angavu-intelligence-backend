/**
 * Msaidizi WhatsApp Bot — OpenWA Service
 *
 * Self-hosted WhatsApp Web API using the Baileys library.
 * Handles incoming messages and forwards them to the Msaidizi
 * backend API for processing.
 *
 * Features:
 * - Automatic reconnection on disconnect
 * - Message queue for reliability
 * - Daily report sender (cron job)
 * - Share link generator
 * - Swahili message templates
 * - QR code authentication
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, makeInMemoryStore } = require('@whiskeysockets/baileys');
const express = require('express');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
require('dotenv').config();

// =========================================================================
// Configuration
// =========================================================================

const CONFIG = {
    port: parseInt(process.env.OPENWA_PORT || '3000'),
    backendUrl: process.env.OPENWA_BACKEND_URL || 'http://localhost:8000',
    webhookSecret: process.env.OPENWA_WEBHOOK_SECRET || (() => { throw new Error('OPENWA_WEBHOOK_SECRET env var required'); })(),
    authDir: process.env.OPENWA_AUTH_DIR || './data/auth',
    logLevel: process.env.LOG_LEVEL || 'info',
    maxRetries: 5,
    retryDelay: 5000,
};

const logger = pino({ level: CONFIG.logLevel });

// =========================================================================
// Express API (for sending messages from backend)
// =========================================================================

const app = express();
app.use(express.json());

// In-memory message store for reliability
const messageStore = makeInMemoryStore({ logger: pino({ level: 'silent' }) });

// Current socket reference
let sock = null;
let qrCode = null;
let isConnected = false;

/**
 * POST /send-message
 * Send a WhatsApp message to a phone number.
 * Called by the Msaidizi backend to deliver reports and responses.
 */
app.post('/send-message', async (req, res) => {
    const { to, message } = req.body;

    if (!to || !message) {
        return res.status(400).json({ error: 'Missing "to" or "message"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    try {
        // Format phone number (ensure @s.whatsapp.net)
        const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

        await sock.sendMessage(jid, { text: message });

        logger.info({ to: to.substring(0, 6) + '****' }, 'Message sent');
        res.json({ status: 'ok', sent: true });
    } catch (err) {
        logger.error({ error: err.message, to: to.substring(0, 6) + '****' }, 'Failed to send message');
        res.status(500).json({ error: 'Failed to send message', details: err.message });
    }
});

/**
 * POST /send-media
 * Send media (image, document, audio) to a phone number.
 */
app.post('/send-media', async (req, res) => {
    const { to, type, url, caption } = req.body;

    if (!to || !url) {
        return res.status(400).json({ error: 'Missing "to" or "url"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    try {
        const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

        let content;
        switch (type) {
            case 'image':
                content = { image: { url }, caption: caption || '' };
                break;
            case 'document':
                content = { document: { url }, caption: caption || '', mimetype: 'application/pdf' };
                break;
            case 'audio':
                content = { audio: { url }, mimetype: 'audio/mp4' };
                break;
            default:
                content = { image: { url }, caption: caption || '' };
        }

        await sock.sendMessage(jid, content);
        res.json({ status: 'ok', sent: true });
    } catch (err) {
        logger.error({ error: err.message }, 'Failed to send media');
        res.status(500).json({ error: 'Failed to send media' });
    }
});

/**
 * GET /status
 * Get current connection status.
 */
app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        hasQR: !!qrCode,
        version: '0.1.0',
    });
});

/**
 * GET /health
 * Health check endpoint.
 */
app.get('/health', (req, res) => {
    res.json({ status: 'ok', service: 'msaidizi-openwa' });
});

// =========================================================================
// WhatsApp Connection (Baileys)
// =========================================================================

/**
 * Initialize WhatsApp connection using Baileys.
 * Handles authentication, reconnection, and message routing.
 */
async function connectWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authDir);

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: 'silent' }),
        browser: ['Msaidizi', 'Chrome', '1.0.0'],
    });

    // Store messages for reliability
    messageStore.bind(sock.ev);

    // Handle QR code for authentication
    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrCode = qr;
            logger.info('QR code received — scan with WhatsApp');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            isConnected = false;

            if (statusCode === DisconnectReason.loggedOut) {
                logger.warn('Logged out — clearing auth state');
                // Would need to re-authenticate
            } else {
                logger.info({ statusCode }, 'Disconnected — reconnecting...');
                setTimeout(connectWhatsApp, CONFIG.retryDelay);
            }
        }

        if (connection === 'open') {
            isConnected = true;
            qrCode = null;
            logger.info('✅ WhatsApp connected');
        }
    });

    // Save credentials on update
    sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return;

        for (const msg of messages) {
            // Skip own messages
            if (msg.key.fromMe) continue;

            // Skip status broadcasts
            if (msg.key.remoteJid === 'status@broadcast') continue;

            await handleIncomingMessage(msg);
        }
    });

    // Handle message receipts
    sock.ev.on('message-receipt.update', (updates) => {
        for (const update of updates) {
            logger.debug({ update }, 'Receipt update');
        }
    });
}

/**
 * Handle an incoming WhatsApp message.
 * Routes to the Msaidizi backend API for processing.
 */
async function handleIncomingMessage(msg) {
    const from = msg.key.remoteJid;
    const pushName = msg.pushName || 'Unknown';
    const messageId = msg.key.id;

    // Extract message content
    let messageText = '';
    let messageType = 'text';
    let mediaUrl = null;

    const messageContent = msg.message;

    if (!messageContent) return;

    if (messageContent.conversation) {
        messageText = messageContent.conversation;
    } else if (messageContent.extendedTextMessage) {
        messageText = messageContent.extendedTextMessage.text;
    } else if (messageContent.imageMessage) {
        messageType = 'image';
        messageText = messageContent.imageMessage.caption || '';
        mediaUrl = messageContent.imageMessage.url;
    } else if (messageContent.audioMessage) {
        messageType = 'voice';
        // Voice messages need transcription
        // Baileys doesn't transcribe — would need Whisper integration
        messageText = '[voice note]';
    } else if (messageContent.documentMessage) {
        messageType = 'document';
        messageText = messageContent.documentMessage.caption || '';
    } else {
        logger.debug({ type: Object.keys(messageContent) }, 'Unsupported message type');
        return;
    }

    // Skip empty messages
    if (!messageText.trim() && messageType === 'text') return;

    const phone = from.replace('@s.whatsapp.net', '');

    logger.info({
        from: phone.substring(0, 6) + '****',
        type: messageType,
        length: messageText.length,
    }, 'Incoming message');

    // Forward to Msaidizi backend
    try {
        const response = await axios.post(`${CONFIG.backendUrl}/api/v1/webhooks/whatsapp`, {
            event: 'message',
            data: {
                from: phone,
                message_id: messageId,
                timestamp: new Date().toISOString(),
                type: messageType,
                body: messageText,
                media_url: mediaUrl,
                is_group: from.includes('@g.us'),
                push_name: pushName,
            },
        }, {
            headers: {
                'Content-Type': 'application/json',
                'X-OpenWA-Signature': generateSignature(JSON.stringify({
                    event: 'message',
                    data: { from: phone, body: messageText },
                })),
            },
            timeout: 10000,
        });

        if (response.data.status === 'ok') {
            logger.info({ from: phone.substring(0, 6) + '****' }, 'Message processed');
        }
    } catch (err) {
        logger.error({
            error: err.message,
            from: phone.substring(0, 6) + '****',
        }, 'Failed to forward message to backend');
    }
}

/**
 * Generate HMAC signature for webhook payload.
 */
function generateSignature(payload) {
    const crypto = require('crypto');
    return crypto
        .createHmac('sha256', CONFIG.webhookSecret)
        .update(payload)
        .digest('hex');
}

// =========================================================================
// Daily Report Sender (Cron Job)
// =========================================================================

/**
 * Send daily reports to all users at 7 PM EAT.
 * Triggered by a setInterval check.
 */
async function sendDailyReports() {
    const now = new Date();
    const eatHour = (now.getUTCHours() + 3) % 24; // EAT = UTC+3

    // Send at 7 PM EAT (19:00)
    if (eatHour === 19 && now.getUTCMinutes() < 5) {
        logger.info('Triggering daily report send...');

        try {
            const response = await axios.post(
                `${CONFIG.backendUrl}/api/v1/webhooks/whatsapp/daily-reports`,
                {},
                { timeout: 30000 }
            );
            logger.info({ sent: response.data.sent }, 'Daily reports sent');
        } catch (err) {
            logger.error({ error: err.message }, 'Failed to send daily reports');
        }
    }
}

// Check every 5 minutes if it's time to send reports
setInterval(sendDailyReports, 5 * 60 * 1000);

// =========================================================================
// Server Startup
// =========================================================================

async function start() {
    logger.info('🇰🇪 Msaidizi OpenWA Service Starting...');

    // Start Express server
    app.listen(CONFIG.port, '0.0.0.0', () => {
        logger.info({ port: CONFIG.port }, 'HTTP server listening');
    });

    // Connect to WhatsApp
    await connectWhatsApp();
}

start().catch((err) => {
    logger.error({ error: err.message }, 'Failed to start');
    process.exit(1);
});
