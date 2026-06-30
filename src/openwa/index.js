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

    async initialize() {
        console.log('[OpenWA] Initializing...');
        try {
            this.client = await create({
                sessionId: process.env.OPENWA_SESSION_ID || 'msaidizi',
                multiDevice: true,
                authTimeout: 60,
                blockCrashLogs: true,
                restartOnCrash: this.handleCrash.bind(this),
                cacheEnabled: false,
                useChrome: true,
                killProcessOnBrowserClose: true,
                throwErrorOnTosBlock: false,
                qrTimeout: 0
            });
            console.log('[OpenWA] Client created');
            this.setupEventHandlers();
            this.reportCronJob.start();
            this.isReady = true;
            console.log('[OpenWA] Integration ready!');
        } catch (error) {
            console.error('[OpenWA] Initialization failed:', error);
            throw error;
        }
    }

    setupEventHandlers() {
        this.client.onMessage(async (message) => {
            try { await this.messageHandler.handleMessage(message); } catch (error) { console.error('[OpenWA] Error handling message:', error); }
        });

        this.client.onAck(async (message) => {
            if (message.ack === 2) console.log(`[OpenWA] Delivered: ${message.id._serialized}`);
            if (message.ack === 3) console.log(`[OpenWA] Read: ${message.id._serialized}`);
        });

        this.client.onStateChanged(async (state) => {
            console.log(`[OpenWA] State: ${state}`);
            if (state === 'CONFLICT' || state === 'UNLAUNCHED') await this.client.forceRefocus();
            if (state === 'DISCONNECTED') await this.handleReconnect();
        });

        this.client.onIncomingCall(async (call) => {
            console.log(`[OpenWA] Rejecting call from ${call.peerJid}`);
            await this.client.rejectCall(call.peerJid);
        });

        console.log('[OpenWA] Event handlers set up');
    }

    async handleCrash() {
        console.log('[OpenWA] Crash detected, restarting...');
        this.isReady = false;
        try { await this.initialize(); } catch (error) {
            console.error('[OpenWA] Restart failed:', error);
            setTimeout(() => this.handleCrash(), 30000);
        }
    }

    async handleReconnect() {
        console.log('[OpenWA] Reconnecting...');
        this.isReady = false;
        let attempts = 0;
        while (attempts < 5) {
            try {
                attempts++;
                await this.sleep(5000);
                await this.client.forceRefocus();
                const state = await this.client.getConnectionState();
                if (state === 'CONNECTED') { console.log('[OpenWA] Reconnected!'); this.isReady = true; return; }
            } catch (error) { console.error(`[OpenWA] Reconnect attempt ${attempts} failed:`, error.message); }
        }
        console.error('[OpenWA] All reconnect attempts failed');
        await this.handleCrash();
    }

    async sendText(phone, message) {
        if (!this.isReady || !this.client) throw new Error('OpenWA not ready');
        const formattedPhone = `${phone.replace('+', '').replace(/\s/g, '')}@c.us`;
        return await this.client.sendText(formattedPhone, message);
    }

    async isRegistered(phone) {
        if (!this.isReady || !this.client) throw new Error('OpenWA not ready');
        const formattedPhone = `${phone.replace('+', '').replace(/\s/g, '')}@c.us`;
        return await this.client.checkNumberStatus(formattedPhone);
    }

    async getConnectionState() {
        if (!this.client) return 'DISCONNECTED';
        return await this.client.getConnectionState();
    }

    sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

    async shutdown() {
        console.log('[OpenWA] Shutting down...');
        this.reportCronJob.stop();
        if (this.client) try { await this.client.kill(); } catch (error) { console.error('[OpenWA] Error closing:', error); }
        this.isReady = false;
    }
}

let instance = null;
function getOpenWAIntegration() { if (!instance) instance = new OpenWAIntegration(); return instance; }
async function initializeOpenWA() { const integration = getOpenWAIntegration(); await integration.initialize(); return integration; }

module.exports = { OpenWAIntegration, getOpenWAIntegration, initializeOpenWA };
