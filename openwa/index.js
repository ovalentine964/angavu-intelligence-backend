/**
 * Msaidizi WhatsApp Bot — OpenWA Service
 *
 * Self-hosted WhatsApp Web API using the Baileys library.
 * Handles incoming messages and forwards them to the Msaidizi
 * backend API for processing.
 *
 * Features:
 * - Automatic reconnection on disconnect (exponential backoff)
 * - Message queue with retry for reliability
 * - QR code authentication
 * - Voice transcription via Whisper STT
 * - Image, document, and audio sending
 * - Health monitoring endpoints
 * - Rate limiting for API protection
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, makeInMemoryStore } = require('@whiskeysockets/baileys');
const express = require('express');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const FormData = require('form-data');
const crypto = require('crypto');
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
    maxRetryDelay: 60000, // 1 minute max backoff
    whisperUrl: process.env.WHISPER_API_URL || 'http://whisper:9000',
    rateLimitWindow: 60000, // 1 minute
    rateLimitMax: 100,      // max requests per window
    messageRetryAttempts: 3,
    messageRetryDelay: 2000,
};

const logger = pino({ level: CONFIG.logLevel });

// =========================================================================
// Rate Limiter (simple in-memory)
// =========================================================================

const rateLimitStore = new Map();

function rateLimit(ip) {
    const now = Date.now();
    const windowStart = now - CONFIG.rateLimitWindow;
    const requests = rateLimitStore.get(ip) || [];
    const recent = requests.filter(t => t > windowStart);
    recent.push(now);
    rateLimitStore.set(ip, recent);
    return recent.length <= CONFIG.rateLimitMax;
}

// Cleanup old entries every 5 minutes
setInterval(() => {
    const cutoff = Date.now() - CONFIG.rateLimitWindow;
    for (const [ip, requests] of rateLimitStore) {
        const recent = requests.filter(t => t > cutoff);
        if (recent.length === 0) rateLimitStore.delete(ip);
        else rateLimitStore.set(ip, recent);
    }
}, 5 * 60 * 1000);

// =========================================================================
// Whisper STT Transcription
// =========================================================================

/**
 * Transcribe audio buffer using Whisper STT.
 * Sends audio to a local Whisper API endpoint for transcription.
 * Supports Swahili, English, and Sheng.
 *
 * @param {Buffer} audioBuffer - Audio data (OGG/Opus from WhatsApp)
 * @returns {Promise<string>} Transcribed text
 */
async function transcribeAudio(audioBuffer) {
    try {
        const form = new FormData();
        form.append('audio_file', audioBuffer, {
            filename: 'voice.ogg',
            contentType: 'audio/ogg',
        });
        form.append('language', 'sw');  // Prefer Swahili

        const response = await axios.post(`${CONFIG.whisperUrl}/asr`, form, {
            headers: form.getHeaders(),
            timeout: 30000,
        });

        const text = response.data?.text || response.data?.transcription || '';
        logger.info({ length: text.length }, 'Voice transcribed');
        return text.trim();
    } catch (err) {
        logger.error({ error: err.message }, 'Whisper transcription failed');
        return '';
    }
}

// =========================================================================
// Message Retry Helper
// =========================================================================

/**
 * Send a message with retry logic.
 *
 * @param {Function} sendFn - Async function that sends the message
 * @param {number} maxAttempts - Maximum retry attempts
 * @returns {Promise<boolean>} True if sent successfully
 */
async function sendWithRetry(sendFn, maxAttempts = CONFIG.messageRetryAttempts) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            await sendFn();
            return true;
        } catch (err) {
            const isLastAttempt = attempt === maxAttempts;
            const isRetryable = !err.message?.includes('not-authorized') &&
                                !err.message?.includes('forbidden');

            if (isLastAttempt || !isRetryable) {
                logger.error({ error: err.message, attempt, maxAttempts }, 'Message send failed (no more retries)');
                return false;
            }

            const delay = CONFIG.messageRetryDelay * attempt;
            logger.warn({ error: err.message, attempt, retryIn: delay }, 'Message send failed, retrying...');
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
    return false;
}

// =========================================================================
// Express API (for sending messages from backend)
// =========================================================================

const app = express();
app.use(express.json({ limit: '10mb' })); // Allow large payloads for base64 images

// Rate limiting middleware
app.use((req, res, next) => {
    if (req.path === '/health' || req.path === '/status') return next();
    const ip = req.ip || req.connection.remoteAddress;
    if (!rateLimit(ip)) {
        return res.status(429).json({ error: 'Rate limit exceeded. Try again later.' });
    }
    next();
});

// Current socket reference
let sock = null;
let qrCode = null;
let isConnected = false;
let lastDisconnect = null;
let reconnectAttempts = 0;
let connectionStartTime = null;

// =========================================================================
// Connection health tracking
// =========================================================================

const healthState = {
    status: 'initializing',
    connected: false,
    lastQrTime: null,
    lastConnectTime: null,
    lastDisconnectTime: null,
    disconnectReason: null,
    reconnectAttempts: 0,
    messagesSent: 0,
    messagesReceived: 0,
    errors: 0,
    uptime: 0,
};

/**
 * POST /send-message
 * Send a WhatsApp text message to a phone number.
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

    const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

    const sent = await sendWithRetry(async () => {
        await sock.sendMessage(jid, { text: message });
    });

    if (sent) {
        healthState.messagesSent++;
        logger.info({ to: to.substring(0, 6) + '****' }, 'Message sent');
        res.json({ status: 'ok', sent: true });
    } else {
        healthState.errors++;
        logger.error({ to: to.substring(0, 6) + '****' }, 'Failed to send message after retries');
        res.status(500).json({ error: 'Failed to send message after retries' });
    }
});

/**
 * POST /send-image
 * Send an image message (base64 or URL) with optional caption.
 * Used by backend to send chart images in reports.
 */
app.post('/send-image', async (req, res) => {
    const { to, image, url, caption } = req.body;

    if (!to) {
        return res.status(400).json({ error: 'Missing "to"' });
    }
    if (!image && !url) {
        return res.status(400).json({ error: 'Missing "image" (base64) or "url"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

    try {
        let imageBuffer;
        if (image) {
            // Base64 encoded image
            imageBuffer = Buffer.from(image, 'base64');
        } else {
            // URL — download first
            const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 15000 });
            imageBuffer = Buffer.from(response.data);
        }

        const sent = await sendWithRetry(async () => {
            await sock.sendMessage(jid, {
                image: imageBuffer,
                caption: caption || '',
                mimetype: 'image/png',
            });
        });

        if (sent) {
            healthState.messagesSent++;
            logger.info({ to: to.substring(0, 6) + '****' }, 'Image sent');
            res.json({ status: 'ok', sent: true });
        } else {
            healthState.errors++;
            res.status(500).json({ error: 'Failed to send image after retries' });
        }
    } catch (err) {
        healthState.errors++;
        logger.error({ error: err.message }, 'Failed to send image');
        res.status(500).json({ error: 'Failed to send image', details: err.message });
    }
});

/**
 * POST /send-voice
 * Send a voice note (audio buffer as base64).
 * Used for low-literacy report delivery.
 */
app.post('/send-voice', async (req, res) => {
    const { to, audio, url } = req.body;

    if (!to) {
        return res.status(400).json({ error: 'Missing "to"' });
    }
    if (!audio && !url) {
        return res.status(400).json({ error: 'Missing "audio" (base64) or "url"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

    try {
        let audioBuffer;
        if (audio) {
            audioBuffer = Buffer.from(audio, 'base64');
        } else {
            const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 15000 });
            audioBuffer = Buffer.from(response.data);
        }

        const sent = await sendWithRetry(async () => {
            await sock.sendMessage(jid, {
                audio: audioBuffer,
                mimetype: 'audio/mp4',
                ptt: true, // Push-to-talk = voice note
            });
        });

        if (sent) {
            healthState.messagesSent++;
            logger.info({ to: to.substring(0, 6) + '****' }, 'Voice note sent');
            res.json({ status: 'ok', sent: true });
        } else {
            healthState.errors++;
            res.status(500).json({ error: 'Failed to send voice note after retries' });
        }
    } catch (err) {
        healthState.errors++;
        logger.error({ error: err.message }, 'Failed to send voice note');
        res.status(500).json({ error: 'Failed to send voice note', details: err.message });
    }
});

/**
 * POST /send-media
 * Send media (image, document, audio) to a phone number.
 * Generic media endpoint — prefer /send-image and /send-voice for those types.
 */
app.post('/send-media', async (req, res) => {
    const { to, type, url, caption, base64 } = req.body;

    if (!to) {
        return res.status(400).json({ error: 'Missing "to"' });
    }
    if (!url && !base64) {
        return res.status(400).json({ error: 'Missing "url" or "base64"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

    try {
        let mediaBuffer;
        if (base64) {
            mediaBuffer = Buffer.from(base64, 'base64');
        } else {
            const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 15000 });
            mediaBuffer = Buffer.from(response.data);
        }

        let content;
        switch (type) {
            case 'image':
                content = { image: mediaBuffer, caption: caption || '' };
                break;
            case 'document':
                content = { document: mediaBuffer, caption: caption || '', mimetype: 'application/pdf' };
                break;
            case 'audio':
                content = { audio: mediaBuffer, mimetype: 'audio/mp4', ptt: false };
                break;
            default:
                content = { image: mediaBuffer, caption: caption || '' };
        }

        const sent = await sendWithRetry(async () => {
            await sock.sendMessage(jid, content);
        });

        if (sent) {
            healthState.messagesSent++;
            res.json({ status: 'ok', sent: true });
        } else {
            healthState.errors++;
            res.status(500).json({ error: 'Failed to send media after retries' });
        }
    } catch (err) {
        healthState.errors++;
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
        version: '0.2.0',
        uptime: connectionStartTime ? Math.floor((Date.now() - connectionStartTime) / 1000) : 0,
        messagesSent: healthState.messagesSent,
        messagesReceived: healthState.messagesReceived,
    });
});

/**
 * GET /health
 * Health check endpoint for container orchestration.
 * Returns 200 if service is running (even if WhatsApp is disconnected).
 * Returns connection status in body for monitoring.
 */
app.get('/health', (req, res) => {
    const health = {
        status: 'ok',
        service: 'msaidizi-openwa',
        version: '0.2.0',
        whatsapp: {
            connected: isConnected,
            hasQR: !!qrCode,
            reconnectAttempts: reconnectAttempts,
            lastDisconnect: lastDisconnect ? {
                time: new Date(lastDisconnect.time).toISOString(),
                reason: lastDisconnect.reason,
            } : null,
        },
        stats: {
            messagesSent: healthState.messagesSent,
            messagesReceived: healthState.messagesReceived,
            errors: healthState.errors,
        },
        uptime: connectionStartTime ? Math.floor((Date.now() - connectionStartTime) / 1000) : 0,
    };

    // If WhatsApp hasn't connected for a long time, report degraded
    if (!isConnected && reconnectAttempts > 10) {
        health.status = 'degraded';
    }

    res.json(health);
});

/**
 * GET /qr
 * Get current QR code for authentication.
 * Returns the QR string if available, or status if already connected.
 */
app.get('/qr', (req, res) => {
    if (isConnected) {
        return res.json({ status: 'connected', message: 'Already connected to WhatsApp' });
    }
    if (qrCode) {
        return res.json({ status: 'qr_available', qr: qrCode });
    }
    return res.json({ status: 'waiting', message: 'Waiting for QR code...' });
});

// =========================================================================
// WhatsApp Connection (Baileys)
// =========================================================================

/**
 * Initialize WhatsApp connection using Baileys.
 * Handles authentication, reconnection with exponential backoff,
 * and message routing.
 */
async function connectWhatsApp() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authDir);

        sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: 'silent' }),
            browser: ['Msaidizi', 'Chrome', '2.0.0'],
            generateHighQualityLinkPreview: false,
        });

        // Handle QR code for authentication
        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect: ld, qr } = update;

            if (qr) {
                qrCode = qr;
                healthState.lastQrTime = Date.now();
                logger.info('QR code received — scan with WhatsApp');
                qrcode.generate(qr, { small: true });
            }

            if (connection === 'close') {
                const statusCode = ld?.error?.output?.statusCode;
                isConnected = false;
                healthState.connected = false;
                healthState.lastDisconnectTime = Date.now();
                lastDisconnect = { time: Date.now(), reason: statusCode };

                if (statusCode === DisconnectReason.loggedOut) {
                    logger.warn('Logged out — clearing auth state. Re-scan required.');
                    healthState.disconnectReason = 'logged_out';
                    // Don't auto-reconnect on logout — user must re-scan
                    healthState.status = 'logged_out';
                } else if (statusCode === DisconnectReason.restartRequired) {
                    logger.info('Restart required — reconnecting...');
                    healthState.disconnectReason = 'restart_required';
                    reconnectAttempts = 0;
                    setTimeout(connectWhatsApp, 1000);
                } else {
                    reconnectAttempts++;
                    healthState.reconnectAttempts = reconnectAttempts;
                    healthState.disconnectReason = `code_${statusCode}`;

                    // Exponential backoff with max delay
                    const delay = Math.min(
                        CONFIG.retryDelay * Math.pow(1.5, reconnectAttempts - 1),
                        CONFIG.maxRetryDelay
                    );

                    logger.info({ statusCode, attempt: reconnectAttempts, retryIn: Math.floor(delay / 1000) }, 'Disconnected — reconnecting...');
                    setTimeout(connectWhatsApp, delay);
                }
            }

            if (connection === 'open') {
                isConnected = true;
                qrCode = null;
                reconnectAttempts = 0;
                connectionStartTime = Date.now();
                healthState.connected = true;
                healthState.lastConnectTime = Date.now();
                healthState.status = 'connected';
                healthState.disconnectReason = null;
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

                healthState.messagesReceived++;
                await handleIncomingMessage(msg);
            }
        });

        // Handle message receipts
        sock.ev.on('message-receipt.update', (updates) => {
            for (const update of updates) {
                logger.debug({ update }, 'Receipt update');
            }
        });

    } catch (err) {
        logger.error({ error: err.message }, 'Failed to initialize WhatsApp connection');
        reconnectAttempts++;
        const delay = Math.min(CONFIG.retryDelay * Math.pow(1.5, reconnectAttempts - 1), CONFIG.maxRetryDelay);
        setTimeout(connectWhatsApp, delay);
    }
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
        // Download audio buffer and transcribe via Whisper STT
        try {
            const buffer = await sock.downloadMediaMessage(msg);
            const transcription = await transcribeAudio(buffer);
            messageText = transcription || '';
        } catch (err) {
            logger.error({ error: err.message }, 'Voice transcription failed');
            messageText = '';
        }
        if (!messageText.trim()) {
            // Send helpful fallback
            const fallbackMsg = '🎤 Sijaweza kusikia voice note yako vizuri.\n\n' +
                'Tafadhali:\n' +
                '• Tuma voice note kwa utulivu\n' +
                '• Au andika ujumbe: "Ripoti ya leo"';
            const jid = msg.key.remoteJid;
            try {
                await sock.sendMessage(jid, { text: fallbackMsg });
            } catch (e) { /* ignore send errors for fallback */ }
            return;
        }
    } else if (messageContent.documentMessage) {
        messageType = 'document';
        messageText = messageContent.documentMessage.caption || '';
    } else if (messageContent.buttonsResponseMessage) {
        // Interactive button response
        messageText = messageContent.buttonsResponseMessage.selectedButtonId || '';
        messageType = 'interactive';
    } else if (messageContent.listResponseMessage) {
        // Interactive list response
        messageText = messageContent.listResponseMessage.singleSelectReply?.selectedRowId || '';
        messageType = 'interactive';
    } else {
        logger.debug({ type: Object.keys(messageContent) }, 'Unsupported message type');
        return;
    }

    // Skip empty messages
    if (!messageText.trim() && messageType === 'text') return;

    const phone = from.replace('@s.whatsapp.net', '').replace('@g.us', '');

    logger.info({
        from: phone.substring(0, 6) + '****',
        type: messageType,
        length: messageText.length,
    }, 'Incoming message');

    // Forward to Msaidizi backend
    try {
        const payload = JSON.stringify({
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
        });

        const response = await axios.post(
            `${CONFIG.backendUrl}/api/v1/webhooks/whatsapp`,
            payload,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-OpenWA-Signature': generateSignature(payload),
                },
                timeout: 15000,
            }
        );

        if (response.data.status === 'ok') {
            logger.info({ from: phone.substring(0, 6) + '****' }, 'Message processed');
        }
    } catch (err) {
        logger.error({
            error: err.message,
            status: err.response?.status,
            from: phone.substring(0, 6) + '****',
        }, 'Failed to forward message to backend');
    }
}

/**
 * Generate HMAC signature for webhook payload.
 */
function generateSignature(payload) {
    return crypto
        .createHmac('sha256', CONFIG.webhookSecret)
        .update(payload)
        .digest('hex');
}

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
