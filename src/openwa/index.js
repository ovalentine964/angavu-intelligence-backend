/**
 * OpenWA Integration — Main Entry Point
 * 
 * This file initializes the OpenWA client and sets up message handlers
 * for the Msaidizi WhatsApp integration.
 * 
 * Features:
 *  - WhatsApp Web connection management
 *  - Incoming message routing
 *  - Report delivery
 *  - Share link generation
 *  - Query handlers (ripoti, mauzo, faida)
 */

const { create } = require('@open-wa/wa-automate');
const MessageHandler = require('./MessageHandler');
const ReportCronJob = require('../services/ReportCronJob');

class OpenWAIntegration {
    constructor() {
        this.client = null;
        this.messageHandler = new MessageHandler();
        this.reportCronJob = new ReportCronJob();
        this.isReady = false;
    }

    /**
     * Initialize OpenWA connection.
     */
    async initialize() {
        console.log('[OpenWA] Initializing...');

        try {
            // Create OpenWA client
            this.client = await create({
                sessionId: process.env.OPENWA_SESSION_ID || 'msaidizi',
                multiDevice: true, // Multi-device support
                authTimeout: 60, // 60 seconds for QR scan
                blockCrashLogs: true,
                restartOnCrash: this.handleCrash.bind(this),
                cacheEnabled: false,
                useChrome: true,
                killProcessOnBrowserClose: true,
                throwErrorOnTosBlock: false,
                qrTimeout: 0, // No QR timeout
                qrLogSkip: false
            });

            console.log('[OpenWA] Client created successfully');

            // Set up event handlers
            this.setupEventHandlers();

            // Start report cron job
            this.reportCronJob.start();

            this.isReady = true;
            console.log('[OpenWA] Integration ready!');

        } catch (error) {
            console.error('[OpenWA] Initialization failed:', error);
            throw error;
        }
    }

    /**
     * Set up event handlers for OpenWA client.
     */
    setupEventHandlers() {
        // Handle incoming messages
        this.client.onMessage(async (message) => {
            try {
                await this.messageHandler.handleMessage(message);
            } catch (error) {
                console.error('[OpenWA] Error handling message:', error);
            }
        });

        // Handle message acknowledgment
        this.client.onAck(async (message) => {
            // Track delivery receipts
            if (message.ack === 2) { // Delivered
                console.log(`[OpenWA] Message delivered: ${message.id._serialized}`);
            }
            if (message.ack === 3) { // Read
                console.log(`[OpenWA] Message read: ${message.id._serialized}`);
            }
        });

        // Handle state changes
        this.client.onStateChanged(async (state) => {
            console.log(`[OpenWA] State changed: ${state}`);

            if (state === 'CONFLICT' || state === 'UNLAUNCHED') {
                await this.client.forceRefocus();
            }

            if (state === 'DISCONNECTED') {
                console.log('[OpenWA] Disconnected! Attempting to reconnect...');
                await this.handleReconnect();
            }
        });

        // Handle incoming calls (reject automatically)
        this.client.onIncomingCall(async (call) => {
            console.log(`[OpenWA] Incoming call from ${call.peerJid}, rejecting...`);
            await this.client.rejectCall(call.peerJid);
        });

        // Handle group join
        this.client.onAddedToGroup(async (chat) => {
            console.log(`[OpenWA] Added to group: ${chat.name}`);
        });

        console.log('[OpenWA] Event handlers set up');
    }

    /**
     * Handle crash and restart.
     */
    async handleCrash() {
        console.log('[OpenWA] Crash detected, restarting...');
        this.isReady = false;

        try {
            await this.initialize();
        } catch (error) {
            console.error('[OpenWA] Restart failed:', error);
            // Schedule retry after 30 seconds
            setTimeout(() => this.handleCrash(), 30000);
        }
    }

    /**
     * Handle reconnection.
     */
    async handleReconnect() {
        console.log('[OpenWA] Attempting reconnection...');
        this.isReady = false;

        let attempts = 0;
        const maxAttempts = 5;

        while (attempts < maxAttempts) {
            try {
                attempts++;
                console.log(`[OpenWA] Reconnection attempt ${attempts}/${maxAttempts}...`);

                await this.sleep(5000); // Wait 5 seconds
                await this.client.forceRefocus();

                const state = await this.client.getConnectionState();
                if (state === 'CONNECTED') {
                    console.log('[OpenWA] Reconnected successfully!');
                    this.isReady = true;
                    return;
                }

            } catch (error) {
                console.error(`[OpenWA] Reconnection attempt ${attempts} failed:`, error.message);
            }
        }

        console.error('[OpenWA] All reconnection attempts failed, restarting...');
        await this.handleCrash();
    }

    /**
     * Send a text message.
     */
    async sendText(phone, message) {
        if (!this.isReady || !this.client) {
            throw new Error('OpenWA not ready');
        }

        const formattedPhone = this.formatPhoneForOpenWA(phone);
        return await this.client.sendText(formattedPhone, message);
    }

    /**
     * Send a media message.
     */
    async sendMedia(phone, mediaUrl, caption, mimeType) {
        if (!this.isReady || !this.client) {
            throw new Error('OpenWA not ready');
        }

        const formattedPhone = this.formatPhoneForOpenWA(phone);
        return await this.client.sendFileFromUrl(formattedPhone, mediaUrl, caption, caption);
    }

    /**
     * Check if a number is registered on WhatsApp.
     */
    async isRegistered(phone) {
        if (!this.isReady || !this.client) {
            throw new Error('OpenWA not ready');
        }

        const formattedPhone = this.formatPhoneForOpenWA(phone);
        return await this.client.checkNumberStatus(formattedPhone);
    }

    /**
     * Get connection state.
     */
    async getConnectionState() {
        if (!this.client) return 'DISCONNECTED';
        return await this.client.getConnectionState();
    }

    /**
     * Format phone for OpenWA.
     */
    formatPhoneForOpenWA(phone) {
        const cleaned = phone.replace('+', '').replace(/\s/g, '');
        return `${cleaned}@c.us`;
    }

    /**
     * Sleep utility.
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Shutdown gracefully.
     */
    async shutdown() {
        console.log('[OpenWA] Shutting down...');

        // Stop report cron job
        this.reportCronJob.stop();

        // Close OpenWA client
        if (this.client) {
            try {
                await this.client.kill();
            } catch (error) {
                console.error('[OpenWA] Error closing client:', error);
            }
        }

        this.isReady = false;
        console.log('[OpenWA] Shutdown complete');
    }
}

// Singleton instance
let instance = null;

/**
 * Get or create the OpenWA integration instance.
 */
function getOpenWAIntegration() {
    if (!instance) {
        instance = new OpenWAIntegration();
    }
    return instance;
}

/**
 * Initialize OpenWA integration.
 */
async function initializeOpenWA() {
    const integration = getOpenWAIntegration();
    await integration.initialize();
    return integration;
}

module.exports = {
    OpenWAIntegration,
    getOpenWAIntegration,
    initializeOpenWA
};
