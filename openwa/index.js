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
 *
 * === BAN RISK MITIGATION (Critical) ===
 * WhatsApp uses Baileys (unofficial library) — Meta could ban the
 * phone number at any time. The following safety measures reduce risk:
 *
 * 1. Human-like delays between messages (2-8 seconds random)
 * 2. Message queue with backpressure (never floods the connection)
 * 3. Rate limiting: max 10 messages/second (configurable)
 * 4. Consecutive message cap: 50 messages, then 60s cooldown
 * 5. Connection health monitoring with ban detection
 * 6. Delivery confirmation tracking
 * 7. Graceful degradation on ban (auto-notify backend)
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
// WhatsApp Safety Configuration
// =========================================================================

const WhatsAppSafetyConfig = {
    // Maximum messages per second (conservative — Baileys risk)
    maxMessagesPerSecond: parseInt(process.env.WA_MAX_MSG_PER_SEC || '10'),

    // Minimum delay between messages (ms) — human-like
    minDelayBetweenMessages: parseInt(process.env.WA_MIN_DELAY_MS || '2000'),

    // Maximum delay between messages (ms) — randomised
    maxDelayBetweenMessages: parseInt(process.env.WA_MAX_DELAY_MS || '8000'),

    // Max consecutive messages before forced cooldown
    maxConsecutiveMessages: parseInt(process.env.WA_MAX_CONSECUTIVE || '50'),

    // Cooldown period after hitting consecutive limit (ms)
    cooldownPeriod: parseInt(process.env.WA_COOLDOWN_MS || '60000'),

    // Max messages per minute (broader rate limit)
    maxMessagesPerMinute: parseInt(process.env.WA_MAX_MSG_PER_MIN || '200'),

    // Time window for per-minute rate limiting (ms)
    rateLimitWindowMs: 60000,

    // Ban detection: max consecutive send failures before flagging
    banDetectionThreshold: parseInt(process.env.WA_BAN_THRESHOLD || '5'),

    // Health check interval (ms)
    healthCheckIntervalMs: parseInt(process.env.WA_HEALTH_INTERVAL_MS || '30000'),

    // Delivery confirmation timeout (ms)
    deliveryConfirmTimeoutMs: parseInt(process.env.WA_DELIVERY_TIMEOUT_MS || '30000'),
};

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
// Rate Limiter (simple in-memory — for HTTP API requests)
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
// WhatsApp Safety Manager
// =========================================================================

/**
 * Manages message sending safety to minimize ban risk.
 * Implements rate limiting, human-like delays, backpressure, and ban detection.
 */
class WhatsAppSafetyManager {
    constructor(config) {
        this.config = config;

        // Message queue (FIFO with priority support)
        this.queue = [];
        this.processing = false;

        // Rate limiting state
        this.sendTimestamps = [];      // timestamps of recent sends
        this.consecutiveSends = 0;     // consecutive messages without cooldown
        this.lastSendTime = 0;         // last message send timestamp
        this.inCooldown = false;       // currently in cooldown period

        // Ban detection state
        this.consecutiveFailures = 0;
        this.banDetected = false;
        this.banDetectedAt = null;
        this.banReason = null;

        // Delivery tracking
        this.deliveryTracker = new Map(); // messageId → { status, timestamp, recipient }

        // Statistics
        this.stats = {
            totalQueued: 0,
            totalSent: 0,
            totalFailed: 0,
            totalDropped: 0,
            totalCooldowns: 0,
            avgDelayMs: 0,
            _delaySum: 0,
            _delayCount: 0,
        };
    }

    /**
     * Enqueue a message for safe delivery.
     * Returns a promise that resolves with the delivery result.
     */
    enqueue(sendFn, metadata = {}) {
        if (this.banDetected) {
            return Promise.resolve({
                success: false,
                error: 'WhatsApp ban detected — refusing to send',
                banDetected: true,
                banReason: this.banReason,
            });
        }

        return new Promise((resolve, reject) => {
            const item = {
                id: crypto.randomUUID(),
                sendFn,
                metadata,
                resolve,
                reject,
                enqueuedAt: Date.now(),
                attempts: 0,
                priority: metadata.priority || 'normal', // 'high', 'normal', 'low'
            };

            // Priority insertion: high priority goes to front
            if (item.priority === 'high') {
                this.queue.unshift(item);
            } else {
                this.queue.push(item);
            }

            this.stats.totalQueued++;
            logger.debug({ queueLength: this.queue.length, id: item.id }, 'Message enqueued');

            // Start processing if not already running
            if (!this.processing) {
                this._processQueue();
            }
        });
    }

    /**
     * Process the message queue with safety delays.
     */
    async _processQueue() {
        if (this.processing) return;
        this.processing = true;

        while (this.queue.length > 0) {
            // Check if we're in cooldown
            if (this.inCooldown) {
                logger.info({ cooldownMs: this.config.cooldownPeriod }, 'In cooldown — waiting');
                await this._sleep(this.config.cooldownPeriod);
                this.inCooldown = false;
                this.consecutiveSends = 0;
                this.stats.totalCooldowns++;
            }

            // Check consecutive message limit
            if (this.consecutiveSends >= this.config.maxConsecutiveMessages) {
                logger.warn(
                    { consecutive: this.consecutiveSends, limit: this.config.maxConsecutiveMessages },
                    'Hit consecutive message limit — entering cooldown'
                );
                this.inCooldown = true;
                continue; // Will wait on next iteration
            }

            // Check per-minute rate limit
            if (!this._checkMinuteRateLimit()) {
                logger.warn('Per-minute rate limit hit — pausing');
                await this._sleep(5000); // Wait 5 seconds and retry
                continue;
            }

            // Calculate human-like delay
            const delay = this._calculateDelay();
            if (delay > 0 && this.stats.totalSent > 0) {
                // Track average delay
                this.stats._delaySum += delay;
                this.stats._delayCount++;
                this.stats.avgDelayMs = Math.round(this.stats._delaySum / this.stats._delayCount);

                logger.debug({ delayMs: delay }, 'Human-like delay before next send');
                await this._sleep(delay);
            }

            // Dequeue and send
            const item = this.queue.shift();
            if (!item) continue;

            item.attempts++;
            const sendStart = Date.now();

            try {
                // Rate limit check (per-second)
                if (!this._checkPerSecondRateLimit()) {
                    // Re-queue at front and wait
                    this.queue.unshift(item);
                    await this._sleep(1000);
                    continue;
                }

                // Execute the actual send
                const result = await item.sendFn();

                // Record success
                const sendDuration = Date.now() - sendStart;
                this.sendTimestamps.push(Date.now());
                this.consecutiveSends++;
                this.lastSendTime = Date.now();
                this.consecutiveFailures = 0; // Reset failure counter

                this.stats.totalSent++;

                // Track delivery
                const messageId = result?.messageId || item.id;
                this._trackDelivery(messageId, item.metadata.recipient, 'sent');

                logger.info(
                    {
                        id: item.id,
                        duration: sendDuration,
                        queueLength: this.queue.length,
                        consecutive: this.consecutiveSends,
                    },
                    'Message sent successfully'
                );

                item.resolve({ success: true, messageId, queueLength: this.queue.length });

            } catch (err) {
                const sendDuration = Date.now() - sendStart;
                this.consecutiveFailures++;
                this.stats.totalFailed++;

                logger.error(
                    {
                        id: item.id,
                        error: err.message,
                        attempt: item.attempts,
                        consecutiveFailures: this.consecutiveFailures,
                        duration: sendDuration,
                    },
                    'Message send failed'
                );

                // Ban detection: check if failures indicate a ban
                if (this._checkForBan(err)) {
                    this.banDetected = true;
                    this.banDetectedAt = Date.now();
                    this.banReason = err.message;
                    this.stats.totalDropped += this.queue.length;

                    logger.fatal(
                        { reason: err.message, consecutiveFailures: this.consecutiveFailures },
                        '🚨 WHATSAPP BAN DETECTED — draining queue'
                    );

                    // Notify backend about ban
                    this._notifyBackendOfBan(err.message).catch(() => {});

                    // Reject all remaining items in queue
                    for (const remaining of this.queue) {
                        remaining.resolve({
                            success: false,
                            error: 'WhatsApp ban detected',
                            banDetected: true,
                        });
                    }
                    this.queue = [];
                    break;
                }

                // Retry logic
                if (item.attempts < CONFIG.messageRetryAttempts) {
                    const retryDelay = CONFIG.messageRetryDelay * item.attempts;
                    logger.warn({ retryIn: retryDelay, attempt: item.attempts }, 'Retrying message');
                    await this._sleep(retryDelay);
                    this.queue.unshift(item); // Re-queue at front
                } else {
                    item.resolve({ success: false, error: err.message, attempts: item.attempts });
                }
            }
        }

        this.processing = false;
    }

    /**
     * Calculate a human-like delay between messages.
     * Random delay between min and max, with jitter.
     */
    _calculateDelay() {
        const { minDelayBetweenMessages, maxDelayBetweenMessages } = this.config;
        const base = minDelayBetweenMessages + Math.random() * (maxDelayBetweenMessages - minDelayBetweenMessages);
        // Add slight jitter (±10%)
        const jitter = base * (Math.random() * 0.2 - 0.1);
        return Math.max(0, Math.floor(base + jitter));
    }

    /**
     * Check per-second rate limit.
     */
    _checkPerSecondRateLimit() {
        const now = Date.now();
        const oneSecAgo = now - 1000;
        this.sendTimestamps = this.sendTimestamps.filter(t => t > oneSecAgo);
        return this.sendTimestamps.length < this.config.maxMessagesPerSecond;
    }

    /**
     * Check per-minute rate limit.
     */
    _checkMinuteRateLimit() {
        const now = Date.now();
        const oneMinAgo = now - this.config.rateLimitWindowMs;
        this.sendTimestamps = this.sendTimestamps.filter(t => t > oneMinAgo);
        return this.sendTimestamps.length < this.config.maxMessagesPerMinute;
    }

    /**
     * Check if a send error indicates a WhatsApp ban.
     */
    _checkForBan(err) {
        if (this.consecutiveFailures >= this.config.banDetectionThreshold) {
            return true;
        }

        const banIndicators = [
            'not-authorized',
            'forbidden',
            'banned',
            'blocked',
            'account suspended',
            'rate-overlimit',
            'too many requests',
        ];

        const errMsg = (err.message || '').toLowerCase();
        return banIndicators.some(indicator => errMsg.includes(indicator));
    }

    /**
     * Track a message delivery status.
     */
    _trackDelivery(messageId, recipient, status) {
        this.deliveryTracker.set(messageId, {
            status,
            recipient,
            timestamp: Date.now(),
            confirmed: false,
        });

        // Auto-cleanup after timeout
        setTimeout(() => {
            const entry = this.deliveryTracker.get(messageId);
            if (entry && !entry.confirmed) {
                entry.status = 'timeout';
                this.deliveryTracker.set(messageId, entry);
            }
        }, this.config.deliveryConfirmTimeoutMs);
    }

    /**
     * Update delivery status from receipt events.
     */
    updateDeliveryStatus(messageId, status) {
        const entry = this.deliveryTracker.get(messageId);
        if (entry) {
            entry.status = status;
            entry.confirmed = true;
            entry.confirmedAt = Date.now();
            this.deliveryTracker.set(messageId, entry);
            logger.debug({ messageId, status }, 'Delivery status updated');
        }
    }

    /**
     * Notify backend that a ban was detected.
     */
    async _notifyBackendOfBan(reason) {
        try {
            await axios.post(
                `${CONFIG.backendUrl}/api/v1/channels/ban-detected`,
                {
                    channel: 'whatsapp',
                    reason,
                    detectedAt: new Date().toISOString(),
                    stats: this.getStats(),
                },
                { timeout: 5000 }
            );
        } catch (err) {
            logger.error({ error: err.message }, 'Failed to notify backend of ban');
        }
    }

    /**
     * Get safety manager statistics.
     */
    getStats() {
        return {
            ...this.stats,
            queueLength: this.queue.length,
            processing: this.processing,
            inCooldown: this.inCooldown,
            consecutiveSends: this.consecutiveSends,
            consecutiveFailures: this.consecutiveFailures,
            banDetected: this.banDetected,
            banDetectedAt: this.banDetectedAt,
            banReason: this.banReason,
            activeDeliveries: this.deliveryTracker.size,
        };
    }

    /**
     * Get delivery status for a specific message.
     */
    getDeliveryStatus(messageId) {
        return this.deliveryTracker.get(messageId) || null;
    }

    /**
     * Get all tracked deliveries.
     */
    getAllDeliveries() {
        const deliveries = {};
        for (const [id, entry] of this.deliveryTracker) {
            deliveries[id] = entry;
        }
        return deliveries;
    }

    /**
     * Reset ban state (use after confirming ban is lifted).
     */
    resetBanState() {
        this.banDetected = false;
        this.banDetectedAt = null;
        this.banReason = null;
        this.consecutiveFailures = 0;
        this.consecutiveSends = 0;
        this.inCooldown = false;
        logger.info('Ban state reset — WhatsApp sending re-enabled');
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Create global safety manager
const safetyManager = new WhatsAppSafetyManager(WhatsAppSafetyConfig);

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
// Message Retry Helper (legacy — prefer safetyManager.enqueue)
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
    if (req.path === '/health' || req.path === '/status' || req.path === '/safety') return next();
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
    // Ban detection
    banDetected: false,
    banDetectedAt: null,
    banReason: null,
};

// =========================================================================
// Health Check Loop
// =========================================================================

let healthCheckInterval = null;

function startHealthCheck() {
    if (healthCheckInterval) clearInterval(healthCheckInterval);

    healthCheckInterval = setInterval(() => {
        // Check if socket is actually alive
        if (isConnected && sock) {
            // Update uptime
            healthState.uptime = connectionStartTime
                ? Math.floor((Date.now() - connectionStartTime) / 1000)
                : 0;
        }

        // Sync ban state from safety manager
        if (safetyManager.banDetected && !healthState.banDetected) {
            healthState.banDetected = true;
            healthState.banDetectedAt = safetyManager.banDetectedAt;
            healthState.banReason = safetyManager.banReason;
            healthState.status = 'banned';
            logger.fatal('Health check: WhatsApp ban confirmed');
        }

        // Log health summary periodically
        const stats = safetyManager.getStats();
        if (stats.totalSent > 0 && stats.totalSent % 50 === 0) {
            logger.info({
                sent: stats.totalSent,
                failed: stats.totalFailed,
                queued: stats.queueLength,
                avgDelay: stats.avgDelayMs,
                cooldowns: stats.totalCooldowns,
                consecutive: stats.consecutiveSends,
            }, 'Safety manager health summary');
        }
    }, WhatsAppSafetyConfig.healthCheckIntervalMs);
}

// =========================================================================
// POST /send-message (via safety manager)
// =========================================================================

/**
 * POST /send-message
 * Send a WhatsApp text message to a phone number.
 * Messages go through the safety manager queue with human-like delays.
 */
app.post('/send-message', async (req, res) => {
    const { to, message, priority } = req.body;

    if (!to || !message) {
        return res.status(400).json({ error: 'Missing "to" or "message"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    if (safetyManager.banDetected) {
        return res.status(503).json({
            error: 'WhatsApp ban detected — sending disabled',
            banReason: safetyManager.banReason,
            banDetectedAt: safetyManager.banDetectedAt,
        });
    }

    const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

    try {
        const result = await safetyManager.enqueue(
            async () => {
                await sock.sendMessage(jid, { text: message });
                healthState.messagesSent++;
                return { sent: true };
            },
            { recipient: to, type: 'text', priority: priority || 'normal' }
        );

        if (result.success) {
            logger.info({ to: to.substring(0, 6) + '****' }, 'Message sent');
            res.json({ status: 'ok', sent: true, queueLength: result.queueLength });
        } else if (result.banDetected) {
            healthState.banDetected = true;
            healthState.banReason = result.banReason;
            res.status(503).json({ error: 'WhatsApp ban detected', ban: true });
        } else {
            healthState.errors++;
            res.status(500).json({ error: result.error || 'Failed to send message' });
        }
    } catch (err) {
        healthState.errors++;
        logger.error({ error: err.message }, 'Send message error');
        res.status(500).json({ error: 'Internal error' });
    }
});

/**
 * POST /send-image
 * Send an image message (base64 or URL) with optional caption.
 */
app.post('/send-image', async (req, res) => {
    const { to, image, url, caption, priority } = req.body;

    if (!to) {
        return res.status(400).json({ error: 'Missing "to"' });
    }
    if (!image && !url) {
        return res.status(400).json({ error: 'Missing "image" (base64) or "url"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    if (safetyManager.banDetected) {
        return res.status(503).json({ error: 'WhatsApp ban detected — sending disabled' });
    }

    const jid = to.includes('@') ? to : `${to.replace(/[^0-9]/g, '')}@s.whatsapp.net`;

    try {
        let imageBuffer;
        if (image) {
            imageBuffer = Buffer.from(image, 'base64');
        } else {
            const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 15000 });
            imageBuffer = Buffer.from(response.data);
        }

        const result = await safetyManager.enqueue(
            async () => {
                await sock.sendMessage(jid, {
                    image: imageBuffer,
                    caption: caption || '',
                    mimetype: 'image/png',
                });
                healthState.messagesSent++;
                return { sent: true };
            },
            { recipient: to, type: 'image', priority: priority || 'normal' }
        );

        if (result.success) {
            logger.info({ to: to.substring(0, 6) + '****' }, 'Image sent');
            res.json({ status: 'ok', sent: true });
        } else if (result.banDetected) {
            res.status(503).json({ error: 'WhatsApp ban detected' });
        } else {
            healthState.errors++;
            res.status(500).json({ error: result.error || 'Failed to send image' });
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
 */
app.post('/send-voice', async (req, res) => {
    const { to, audio, url, priority } = req.body;

    if (!to) {
        return res.status(400).json({ error: 'Missing "to"' });
    }
    if (!audio && !url) {
        return res.status(400).json({ error: 'Missing "audio" (base64) or "url"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    if (safetyManager.banDetected) {
        return res.status(503).json({ error: 'WhatsApp ban detected — sending disabled' });
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

        const result = await safetyManager.enqueue(
            async () => {
                await sock.sendMessage(jid, {
                    audio: audioBuffer,
                    mimetype: 'audio/mp4',
                    ptt: true,
                });
                healthState.messagesSent++;
                return { sent: true };
            },
            { recipient: to, type: 'voice', priority: priority || 'normal' }
        );

        if (result.success) {
            logger.info({ to: to.substring(0, 6) + '****' }, 'Voice note sent');
            res.json({ status: 'ok', sent: true });
        } else if (result.banDetected) {
            res.status(503).json({ error: 'WhatsApp ban detected' });
        } else {
            healthState.errors++;
            res.status(500).json({ error: result.error || 'Failed to send voice note' });
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
 */
app.post('/send-media', async (req, res) => {
    const { to, type, url, caption, base64, priority } = req.body;

    if (!to) {
        return res.status(400).json({ error: 'Missing "to"' });
    }
    if (!url && !base64) {
        return res.status(400).json({ error: 'Missing "url" or "base64"' });
    }

    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp not connected' });
    }

    if (safetyManager.banDetected) {
        return res.status(503).json({ error: 'WhatsApp ban detected — sending disabled' });
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

        const result = await safetyManager.enqueue(
            async () => {
                await sock.sendMessage(jid, content);
                healthState.messagesSent++;
                return { sent: true };
            },
            { recipient: to, type: type || 'media', priority: priority || 'normal' }
        );

        if (result.success) {
            res.json({ status: 'ok', sent: true });
        } else if (result.banDetected) {
            res.status(503).json({ error: 'WhatsApp ban detected' });
        } else {
            healthState.errors++;
            res.status(500).json({ error: result.error || 'Failed to send media' });
        }
    } catch (err) {
        healthState.errors++;
        logger.error({ error: err.message }, 'Failed to send media');
        res.status(500).json({ error: 'Failed to send media' });
    }
});

// =========================================================================
// Safety & Status Endpoints
// =========================================================================

/**
 * GET /safety
 * Get safety manager statistics and state.
 */
app.get('/safety', (req, res) => {
    const stats = safetyManager.getStats();
    res.json({
        config: WhatsAppSafetyConfig,
        state: stats,
        health: {
            connected: isConnected,
            banDetected: healthState.banDetected,
            banReason: healthState.banReason,
        },
    });
});

/**
 * POST /safety/reset-ban
 * Reset ban state after confirming the number is not banned.
 */
app.post('/safety/reset-ban', (req, res) => {
    safetyManager.resetBanState();
    healthState.banDetected = false;
    healthState.banReason = null;
    healthState.status = isConnected ? 'connected' : 'disconnected';
    res.json({ status: 'ok', message: 'Ban state reset' });
});

/**
 * GET /delivery/:messageId
 * Check delivery status for a specific message.
 */
app.get('/delivery/:messageId', (req, res) => {
    const status = safetyManager.getDeliveryStatus(req.params.messageId);
    if (status) {
        res.json(status);
    } else {
        res.status(404).json({ error: 'Message not found in delivery tracker' });
    }
});

/**
 * GET /delivery
 * Get all tracked deliveries.
 */
app.get('/delivery', (req, res) => {
    res.json(safetyManager.getAllDeliveries());
});

/**
 * GET /status
 * Get current connection status.
 */
app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        hasQR: !!qrCode,
        version: '0.3.0',
        uptime: connectionStartTime ? Math.floor((Date.now() - connectionStartTime) / 1000) : 0,
        messagesSent: healthState.messagesSent,
        messagesReceived: healthState.messagesReceived,
        banDetected: safetyManager.banDetected,
    });
});

/**
 * GET /health
 * Health check endpoint for container orchestration.
 */
app.get('/health', (req, res) => {
    const safetyStats = safetyManager.getStats();
    const health = {
        status: 'ok',
        service: 'msaidizi-openwa',
        version: '0.3.0',
        whatsapp: {
            connected: isConnected,
            hasQR: !!qrCode,
            reconnectAttempts: reconnectAttempts,
            banDetected: safetyManager.banDetected,
            banReason: safetyManager.banReason,
            lastDisconnect: lastDisconnect ? {
                time: new Date(lastDisconnect.time).toISOString(),
                reason: lastDisconnect.reason,
            } : null,
        },
        safety: {
            queueLength: safetyStats.queueLength,
            consecutiveSends: safetyStats.consecutiveSends,
            consecutiveFailures: safetyStats.consecutiveFailures,
            inCooldown: safetyStats.inCooldown,
            avgDelayMs: safetyStats.avgDelayMs,
        },
        stats: {
            messagesSent: healthState.messagesSent,
            messagesReceived: healthState.messagesReceived,
            errors: healthState.errors,
            totalQueued: safetyStats.totalQueued,
            totalSent: safetyStats.totalSent,
            totalFailed: safetyStats.totalFailed,
            totalCooldowns: safetyStats.totalCooldowns,
        },
        uptime: connectionStartTime ? Math.floor((Date.now() - connectionStartTime) / 1000) : 0,
    };

    // If WhatsApp hasn't connected for a long time, report degraded
    if (!isConnected && reconnectAttempts > 10) {
        health.status = 'degraded';
    }
    if (safetyManager.banDetected) {
        health.status = 'banned';
    }

    res.json(health);
});

/**
 * GET /qr
 * Get current QR code for authentication.
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
 * message routing, and delivery receipt tracking.
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

                // Check if this is a ban-related disconnect
                const isBanDisconnect = [
                    DisconnectReason.loggedOut,
                    401, 403, 405,
                ].includes(statusCode);

                if (statusCode === DisconnectReason.loggedOut) {
                    logger.warn('Logged out — clearing auth state. Re-scan required.');
                    healthState.disconnectReason = 'logged_out';
                    healthState.status = 'logged_out';

                    // Check if this might be a ban (not just a manual logout)
                    if (safetyManager.consecutiveFailures > 0) {
                        logger.fatal('Logged out after consecutive failures — likely ban');
                        safetyManager.banDetected = true;
                        safetyManager.banDetectedAt = Date.now();
                        safetyManager.banReason = 'logged_out_after_failures';
                        healthState.banDetected = true;
                        healthState.banReason = 'logged_out_after_failures';
                    }
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

        // Handle message receipts (delivery confirmations)
        sock.ev.on('message-receipt.update', (updates) => {
            for (const update of updates) {
                const { key, receipt } = update;
                const messageId = key?.id;
                if (!messageId) continue;

                // receipt.type: 1=delivered, 2=read, 3=played
                let status = 'unknown';
                if (receipt?.type === 1) status = 'delivered';
                else if (receipt?.type === 2) status = 'read';
                else if (receipt?.type === 3) status = 'played';

                safetyManager.updateDeliveryStatus(messageId, status);
                logger.debug({ messageId, status }, 'Delivery receipt received');
            }
        });

        // Handle message acks
        sock.ev.on('messages.update', (updates) => {
            for (const update of updates) {
                const messageId = update.key?.id;
                if (!messageId) continue;

                // ack values: 0=pending, 1=server, 2=device, 3=read, 4=played
                const ackMap = { 0: 'pending', 1: 'server_ack', 2: 'device_ack', 3: 'read', 4: 'played' };
                const status = ackMap[update.update?.ack] || 'unknown';

                if (status !== 'pending') {
                    safetyManager.updateDeliveryStatus(messageId, status);
                }
            }
        });

        // Start health check loop
        startHealthCheck();

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
        messageText = messageContent.buttonsResponseMessage.selectedButtonId || '';
        messageType = 'interactive';
    } else if (messageContent.listResponseMessage) {
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
    logger.info({
        safety: {
            maxMsgPerSec: WhatsAppSafetyConfig.maxMessagesPerSecond,
            minDelay: WhatsAppSafetyConfig.minDelayBetweenMessages,
            maxDelay: WhatsAppSafetyConfig.maxDelayBetweenMessages,
            maxConsecutive: WhatsAppSafetyConfig.maxConsecutiveMessages,
            cooldown: WhatsAppSafetyConfig.cooldownPeriod,
        },
    }, 'WhatsApp Safety Config loaded');

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
