const axios = require('axios');

class OpenWAClient {
    static instance = null;

    static getInstance() {
        if (!OpenWAClient.instance) OpenWAClient.instance = new OpenWAClient();
        return OpenWAClient.instance;
    }

    constructor() {
        this.baseUrl = process.env.OPENWA_API_URL || 'http://localhost:8080';
        this.apiKey = process.env.OPENWA_API_KEY || '';
        this.sessionId = process.env.OPENWA_SESSION_ID || 'default';
        this.client = axios.create({ baseURL: this.baseUrl, headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.apiKey}` }, timeout: 30000 });
    }

    async isRegistered(phone) {
        try {
            const formattedPhone = phone.replace('+', '');
            const response = await this.client.post(`/session/${this.sessionId}/check-number`, { phone: formattedPhone });
            return response.data && response.data.isRegistered === true;
        } catch (error) {
            console.error('[OpenWA] Error checking registration:', error.message);
            if (error.response && error.response.status === 404) return await this.isRegisteredAlternative(phone);
            throw error;
        }
    }

    async isRegisteredAlternative(phone) {
        try {
            const formattedPhone = phone.replace('+', '');
            const response = await this.client.get(`/session/${this.sessionId}/contact/${formattedPhone}`);
            return response.data && response.data.exists === true;
        } catch (error) { console.warn('[OpenWA] Could not verify registration, assuming registered'); return true; }
    }

    async sendText(phone, message) {
        try {
            const formattedPhone = this.formatPhoneForOpenWA(phone);
            const response = await this.client.post(`/session/${this.sessionId}/send-text`, { to: formattedPhone, message });
            if (response.data && response.data.id) { console.log(`[OpenWA] Message sent to ${phone}`); return response.data; }
            throw new Error('No message ID returned');
        } catch (error) {
            console.error(`[OpenWA] Error sending to ${phone}:`, error.message);
            if (error.response) {
                if (error.response.status === 404 || (error.response.data && error.response.data.error?.includes('not registered'))) throw new Error('Number not registered on WhatsApp');
                if (error.response.status === 429) throw new Error('Rate limited by OpenWA');
            }
            throw error;
        }
    }

    async sendMedia(phone, mediaUrl, caption) {
        try {
            const formattedPhone = this.formatPhoneForOpenWA(phone);
            return await this.client.post(`/session/${this.sessionId}/send-media`, { to: formattedPhone, file: mediaUrl, caption: caption || '' });
        } catch (error) { console.error(`[OpenWA] Error sending media to ${phone}:`, error.message); throw error; }
    }

    formatPhoneForOpenWA(phone) { return `${phone.replace('+', '').replace(/\s/g, '')}@c.us`; }

    async isConnected() {
        try { const response = await this.client.get(`/session/${this.sessionId}/status`); return response.data && response.data.state === 'CONNECTED'; }
        catch (error) { console.error('[OpenWA] Connection check failed:', error.message); return false; }
    }

    async getQRCode() {
        try { const response = await this.client.get(`/session/${this.sessionId}/qr`); return response.data && response.data.qr; }
        catch (error) { console.error('[OpenWA] Error getting QR:', error.message); throw error; }
    }

    async restartSession() {
        try { const response = await this.client.post(`/session/${this.sessionId}/restart`); return response.data && response.data.success === true; }
        catch (error) { console.error('[OpenWA] Error restarting:', error.message); return false; }
    }
}

module.exports = OpenWAClient;
