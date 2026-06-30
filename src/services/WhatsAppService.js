/**
 * WhatsAppService — Backend service for WhatsApp connection management.
 * 
 * Handles:
 *  - Phone number validation (Kenyan format)
 *  - Verification record management
 *  - OpenWA message sending
 *  - Report generation and delivery
 *  - Connection state management
 */

const { v4: uuidv4 } = require('uuid');
const PhoneValidator = require('../utils/PhoneValidator');
const OpenWAClient = require('../openwa/OpenWAClient');
const ReportGenerator = require('../services/ReportGenerator');

// In-memory stores (replace with database in production)
const verifications = new Map();
const connections = new Map();

class WhatsAppService {

    /**
     * Check if a phone number is on WhatsApp via OpenWA.
     */
    static async checkNumberOnWhatsApp(phone) {
        try {
            const client = OpenWAClient.getInstance();
            return await client.isRegistered(phone);
        } catch (error) {
            console.error('Error checking WhatsApp registration:', error);
            // If we can't check, assume it's on WhatsApp (fail-open)
            // The verification message will fail if it's not
            return true;
        }
    }

    /**
     * Create a verification record.
     */
    static async createVerification({ phone, userId, userName, assistantName, language, reportTime }) {
        const verificationId = uuidv4();
        const code = Math.random().toString().slice(2, 6); // 4-digit code (optional)

        const verification = {
            id: verificationId,
            phone,
            userId,
            userName,
            assistantName,
            language,
            reportTime,
            code,
            status: 'pending',
            createdAt: Date.now(),
            whatsappId: null
        };

        verifications.set(verificationId, verification);

        // Auto-expire after 5 minutes
        setTimeout(() => {
            const v = verifications.get(verificationId);
            if (v && v.status === 'pending') {
                v.status = 'expired';
                verifications.set(verificationId, v);
            }
        }, 5 * 60 * 1000);

        console.log(`[WhatsApp] Created verification ${verificationId} for ${phone}`);
        return verification;
    }

    /**
     * Get a verification record by ID.
     */
    static async getVerification(verificationId) {
        return verifications.get(verificationId) || null;
    }

    /**
     * Mark verification as expired.
     */
    static async markVerificationExpired(verificationId) {
        const v = verifications.get(verificationId);
        if (v) {
            v.status = 'expired';
            verifications.set(verificationId, v);
        }
    }

    /**
     * Send verification/welcome message via OpenWA.
     */
    static async sendVerificationMessage({ phone, verificationId, userName, assistantName, language }) {
        try {
            const client = OpenWAClient.getInstance();

            // Build welcome message based on language
            const message = this.buildWelcomeMessage({
                userName,
                assistantName,
                language,
                verificationId
            });

            // Send via OpenWA
            const result = await client.sendText(phone, message);

            if (result && result.id) {
                console.log(`[WhatsApp] Verification message sent to ${phone}, msgId: ${result.id._serialized}`);
                return { success: true, messageId: result.id._serialized };
            }

            return { success: false, error: 'NO_RESULT' };

        } catch (error) {
            console.error('[WhatsApp] Error sending verification message:', error);

            // Check for specific OpenWA errors
            if (error.message && error.message.includes('not registered')) {
                return { success: false, error: 'NOT_ON_WHATSAPP' };
            }

            return { success: false, error: 'SEND_FAILED' };
        }
    }

    /**
     * Build welcome message in the appropriate language.
     */
    static buildWelcomeMessage({ userName, assistantName, language, verificationId }) {
        const messages = {
            sw: `🎉 Habari ${userName}!\n\n${assistantName} wako ameunganishwa na Msaidizi wa Biashara!\n\nSasa utapata:\n📊 Ripoti za biashara kila siku\n💰 Muhtasari wa mauzo na faida\n💡 Vidokezo vya kuboresha biashara\n\nKaribu! 🚀\n\n_Tuma "ripoti" kupata ripoti ya leo_\n_Tuma "mauzo" kupata muhtasari wa mauzo_\n_Tuma "faida" kupata muhtasari wa faida_`,

            sheng: `🎉 Sana ${userName}!\n\n${assistantName} wako ame-connect na Msaidizi wa Biashara! 💪\n\nSasa utapata:\n📊 Report ya biashara daily\n💰 Sales na profit summary\n💡 Tips za kuboressha biashara\n\nKaribu boss! 🔥\n\n_Tuma "ripoti" kwa report ya leo_\n_Tuma "mauzo" kwa sales summary_\n_Tuma "faida" kwa profit summary_`,

            en: `🎉 Hello ${userName}!\n\n${assistantName} is now connected to Msaidizi Business Assistant!\n\nYou'll receive:\n📊 Daily business reports\n💰 Sales and profit summaries\n💡 Tips to grow your business\n\nWelcome aboard! 🚀\n\n_Send "report" for today's report_\n_Send "sales" for sales summary_\n_Send "profit" for profit summary_`
        };

        return messages[language] || messages.sw;
    }

    /**
     * Send confirmation message after successful connection.
     */
    static async sendConfirmationMessage({ phone, userName, assistantName, language }) {
        try {
            const client = OpenWAClient.getInstance();

            const messages = {
                sw: `✅ Umefanikiwa!\n\nSawa ${userName}! Sasa kila jioni ${assistantName} atakutumia muhtasari wa mauzo yako, faida, na vidokezo kupitia WhatsApp.\n\n📱 ${assistantName} — Msaidizi wako wa Biashara`,
                sheng: `✅ Imeisha!\n\nPoa ${userName}! Sasa kila evening ${assistantName} atakutumia sales report, profit na tips kwa WhatsApp.\n\n📱 ${assistantName} — Boy wako wa Biashara 💪`,
                en: `✅ Connected!\n\nGreat ${userName}! Every evening ${assistantName} will send you a summary of your sales, profits, and tips via WhatsApp.\n\n📱 ${assistantName} — Your Business Assistant`
            };

            const message = messages[language] || messages.sw;
            await client.sendText(phone, message);

            console.log(`[WhatsApp] Confirmation sent to ${phone}`);
            return { success: true };

        } catch (error) {
            console.error('[WhatsApp] Error sending confirmation:', error);
            return { success: false };
        }
    }

    /**
     * Connect a user's WhatsApp number to their account.
     */
    static async connectUser({ userId, phone, assistantName, language, reportTime }) {
        const connection = {
            id: uuidv4(),
            userId,
            phone,
            connected: true,
            connectedAt: new Date().toISOString(),
            assistantName,
            language,
            reportTime,
            lastReportSent: null,
            userName: null // Will be set when we have it
        };

        connections.set(userId, connection);

        console.log(`[WhatsApp] Connected user ${userId} to ${phone}`);
        return connection;
    }

    /**
     * Get a user's WhatsApp connection.
     */
    static async getConnection(userId) {
        return connections.get(userId) || null;
    }

    /**
     * Disconnect a user's WhatsApp.
     */
    static async disconnectUser(userId) {
        const connection = connections.get(userId);
        if (connection) {
            connection.connected = false;
            connections.set(userId, connection);
        }
        console.log(`[WhatsApp] Disconnected user ${userId}`);
    }

    /**
     * Update last report sent timestamp.
     */
    static async updateLastReportSent(userId) {
        const connection = connections.get(userId);
        if (connection) {
            connection.lastReportSent = new Date().toISOString();
            connections.set(userId, connection);
        }
    }

    /**
     * Generate a report for a user.
     */
    static async generateReport({ userId, reportType, date, assistantName, userName, language }) {
        const generator = new ReportGenerator();
        return await generator.generate({
            userId,
            reportType,
            date,
            assistantName,
            userName,
            language
        });
    }

    /**
     * Send a report via WhatsApp.
     */
    static async sendReport({ phone, report, language }) {
        try {
            const client = OpenWAClient.getInstance();
            const result = await client.sendText(phone, report);

            if (result && result.id) {
                console.log(`[WhatsApp] Report sent to ${phone}, msgId: ${result.id._serialized}`);
                return { success: true, messageId: result.id._serialized };
            }

            return { success: false };

        } catch (error) {
            console.error('[WhatsApp] Error sending report:', error);
            return { success: false };
        }
    }

    /**
     * Get all connected users (for cron job).
     */
    static async getAllConnectedUsers() {
        const connected = [];
        for (const [userId, connection] of connections) {
            if (connection.connected) {
                connected.push(connection);
            }
        }
        return connected;
    }

    /**
     * Get users who should receive reports at a specific time.
     */
    static async getUsersForReportTime(reportTime) {
        const allUsers = await this.getAllConnectedUsers();
        return allUsers.filter(u => u.reportTime === reportTime);
    }
}

module.exports = WhatsAppService;
