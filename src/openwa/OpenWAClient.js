/**
 * OpenWAClient — Wrapper around OpenWA for sending WhatsApp messages.
 * 
 * This client handles:
 *  - Sending text messages
 *  - Checking if a number is registered on WhatsApp
 *  - Sending media (images, documents)
 *  - Handling delivery receipts
 * 
 * Uses OpenWA's REST API or WebSocket connection.
 */

const axios = require('axios');

class OpenWAClient {
    static instance = null;

    /**
     * Get singleton instance of OpenWA client.
     */
    static getInstance() {
        if (!OpenWAClient.instance) {
            OpenWAClient.instance = new OpenWAClient();
        }
        return OpenWAClient.instance;
    }

    constructor() {
        this.baseUrl = process.env.OPENWA_API_URL || 'http://localhost:8080';
        this.apiKey = process.env.OPENWA_API_KEY || '';
        this.sessionId = process.env.OPENWA_SESSION_ID || 'default';
        this.client = axios.create({
            baseURL: this.baseUrl,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.apiKey}`
            },
            timeout: 30000
        });
    }

    /**
     * Check if a phone number is registered on WhatsApp.
     * 
     * @param {string} phone - Phone number in international format (+254...)
     * @returns {Promise<boolean>}
     */
    async isRegistered(phone) {
        try {
            // Format phone for OpenWA (remove + prefix)
            const formattedPhone = phone.replace('+', '');

            const response = await this.client.post(`/session/${this.sessionId}/check-number`, {
                phone: formattedPhone
            });

            return response.data && response.data.isRegistered === true;

        } catch (error) {
            console.error('[OpenWA] Error checking registration:', error.message);

            // If the endpoint doesn't exist, try alternative method
            if (error.response && error.response.status === 404) {
                return await this.isRegisteredAlternative(phone);
            }

            throw error;
        }
    }

    /**
     * Alternative method to check if number is on WhatsApp.
     * Uses the contact check endpoint.
     */
    async isRegisteredAlternative(phone) {
        try {
            const formattedPhone = phone.replace('+', '');
            const response = await this.client.get(
                `/session/${this.sessionId}/contact/${formattedPhone}`
            );

            return response.data && response.data.exists === true;

        } catch (error) {
            // If we can't check, assume it's registered (fail-open)
            console.warn('[OpenWA] Could not verify registration, assuming registered');
            return true;
        }
    }

    /**
     * Send a text message via WhatsApp.
     * 
     * @param {string} phone - Phone number in international format (+254...)
     * @param {string} message - Message text (supports WhatsApp formatting)
     * @returns {Promise<Object>} Message result with id
     */
    async sendText(phone, message) {
        try {
            // Format phone for OpenWA (add @c.us suffix)
            const formattedPhone = this.formatPhoneForOpenWA(phone);

            const response = await this.client.post(`/session/${this.sessionId}/send-text`, {
                to: formattedPhone,
                message: message
            });

            if (response.data && response.data.id) {
                console.log(`[OpenWA] Message sent to ${phone}, id: ${response.data.id._serialized || response.data.id}`);
                return response.data;
            }

            throw new Error('No message ID returned');

        } catch (error) {
            console.error(`[OpenWA] Error sending message to ${phone}:`, error.message);

            // Check for specific errors
            if (error.response) {
                const status = error.response.status;
                const data = error.response.data;

                if (status === 404 || (data && data.error && data.error.includes('not registered'))) {
                    throw new Error('Number not registered on WhatsApp');
                }

                if (status === 429) {
                    throw new Error('Rate limited by OpenWA');
                }

                if (status === 401 || status === 403) {
                    throw new Error('OpenWA authentication failed');
                }
            }

            throw error;
        }
    }

    /**
     * Send a media message (image, document, etc.).
     * 
     * @param {string} phone - Phone number
     * @param {string} mediaUrl - URL or base64 of the media
     * @param {string} caption - Caption text
     * @param {string} mimeType - MIME type (image/png, application/pdf, etc.)
     * @returns {Promise<Object>}
     */
    async sendMedia(phone, mediaUrl, caption, mimeType) {
        try {
            const formattedPhone = this.formatPhoneForOpenWA(phone);

            const response = await this.client.post(`/session/${this.sessionId}/send-media`, {
                to: formattedPhone,
                file: mediaUrl,
                caption: caption || '',
                mimeType: mimeType || 'image/png'
            });

            return response.data;

        } catch (error) {
            console.error(`[OpenWA] Error sending media to ${phone}:`, error.message);
            throw error;
        }
    }

    /**
     * Send a location message.
     * 
     * @param {string} phone - Phone number
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     * @param {string} title - Location title
     * @returns {Promise<Object>}
     */
    async sendLocation(phone, lat, lng, title) {
        try {
            const formattedPhone = this.formatPhoneForOpenWA(phone);

            const response = await this.client.post(`/session/${this.sessionId}/send-location`, {
                to: formattedPhone,
                lat: lat,
                lng: lng,
                title: title || 'Location'
            });

            return response.data;

        } catch (error) {
            console.error(`[OpenWA] Error sending location to ${phone}:`, error.message);
            throw error;
        }
    }

    /**
     * Get message delivery status.
     * 
     * @param {string} messageId - Message ID
     * @returns {Promise<Object>}
     */
    async getMessageStatus(messageId) {
        try {
            const response = await this.client.get(
                `/session/${this.sessionId}/message/${messageId}/status`
            );

            return response.data;

        } catch (error) {
            console.error(`[OpenWA] Error getting message status:`, error.message);
            throw error;
        }
    }

    /**
     * Format phone number for OpenWA.
     * +254712345678 → 254712345678@c.us
     */
    formatPhoneForOpenWA(phone) {
        const cleaned = phone.replace('+', '').replace(/\s/g, '');
        return `${cleaned}@c.us`;
    }

    /**
     * Check if OpenWA is connected and ready.
     * 
     * @returns {Promise<boolean>}
     */
    async isConnected() {
        try {
            const response = await this.client.get(`/session/${this.sessionId}/status`);
            return response.data && response.data.state === 'CONNECTED';
        } catch (error) {
            console.error('[OpenWA] Connection check failed:', error.message);
            return false;
        }
    }

    /**
     * Get QR code for WhatsApp Web connection.
     * Used for initial setup.
     * 
     * @returns {Promise<string>} QR code data URL
     */
    async getQRCode() {
        try {
            const response = await this.client.get(`/session/${this.sessionId}/qr`);
            return response.data && response.data.qr;
        } catch (error) {
            console.error('[OpenWA] Error getting QR code:', error.message);
            throw error;
        }
    }

    /**
     * Restart the OpenWA session.
     * Useful when connection drops.
     * 
     * @returns {Promise<boolean>}
     */
    async restartSession() {
        try {
            const response = await this.client.post(`/session/${this.sessionId}/restart`);
            return response.data && response.data.success === true;
        } catch (error) {
            console.error('[OpenWA] Error restarting session:', error.message);
            return false;
        }
    }
}

module.exports = OpenWAClient;
