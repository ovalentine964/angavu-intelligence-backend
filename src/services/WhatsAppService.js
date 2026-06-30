const { v4: uuidv4 } = require('uuid');
const PhoneValidator = require('../utils/PhoneValidator');
const OpenWAClient = require('../openwa/OpenWAClient');
const ReportGenerator = require('../services/ReportGenerator');

const verifications = new Map();
const connections = new Map();

class WhatsAppService {
    static async checkNumberOnWhatsApp(phone) {
        try {
            const client = OpenWAClient.getInstance();
            return await client.isRegistered(phone);
        } catch (error) {
            console.error('Error checking WhatsApp registration:', error);
            return true;
        }
    }

    static async createVerification({ phone, userId, userName, assistantName, language, reportTime }) {
        const verificationId = uuidv4();
        const code = Math.random().toString().slice(2, 6);
        const verification = { id: verificationId, phone, userId, userName, assistantName, language, reportTime, code, status: 'pending', createdAt: Date.now(), whatsappId: null };
        verifications.set(verificationId, verification);
        setTimeout(() => { const v = verifications.get(verificationId); if (v && v.status === 'pending') { v.status = 'expired'; verifications.set(verificationId, v); } }, 5 * 60 * 1000);
        console.log(`[WhatsApp] Created verification ${verificationId} for ${phone}`);
        return verification;
    }

    static async getVerification(verificationId) { return verifications.get(verificationId) || null; }
    static async markVerificationExpired(verificationId) { const v = verifications.get(verificationId); if (v) { v.status = 'expired'; verifications.set(verificationId, v); } }

    static async sendVerificationMessage({ phone, verificationId, userName, assistantName, language }) {
        try {
            const client = OpenWAClient.getInstance();
            const message = this.buildWelcomeMessage({ userName, assistantName, language, verificationId });
            const result = await client.sendText(phone, message);
            if (result && result.id) { console.log(`[WhatsApp] Verification message sent to ${phone}`); return { success: true, messageId: result.id._serialized }; }
            return { success: false, error: 'NO_RESULT' };
        } catch (error) {
            console.error('[WhatsApp] Error sending verification message:', error);
            if (error.message && error.message.includes('not registered')) return { success: false, error: 'NOT_ON_WHATSAPP' };
            return { success: false, error: 'SEND_FAILED' };
        }
    }

    static buildWelcomeMessage({ userName, assistantName, language }) {
        const messages = {
            sw: `🎉 Habari ${userName}!\n\n${assistantName} wako ameunganishwa na Msaidizi wa Biashara!\n\nSasa utapata:\n📊 Ripoti za biashara kila siku\n💰 Muhtasari wa mauzo na faida\n💡 Vidokezo vya kuboresha biashara\n\nKaribu! 🚀\n\n_Tuma "ripoti" kupata ripoti ya leo_\n_Tuma "mauzo" kupata muhtasari wa mauzo_\n_Tuma "faida" kupata muhtasari wa faida_`,
            sheng: `🎉 Sana ${userName}!\n\n${assistantName} wako ame-connect na Msaidizi wa Biashara! 💪\n\nSasa utapata:\n📊 Report ya biashara daily\n💰 Sales na profit summary\n💡 Tips za kuboresha biashara\n\nKaribu boss! 🔥`,
            en: `🎉 Hello ${userName}!\n\n${assistantName} is now connected to Msaidizi Business Assistant!\n\nYou'll receive:\n📊 Daily business reports\n💰 Sales and profit summaries\n💡 Tips to grow your business\n\nWelcome aboard! 🚀`
        };
        return messages[language] || messages.sw;
    }

    static async sendConfirmationMessage({ phone, userName, assistantName, language }) {
        try {
            const client = OpenWAClient.getInstance();
            const messages = {
                sw: `✅ Umefanikiwa!\n\nSawa ${userName}! Sasa kila jioni ${assistantName} atakutumia muhtasari wa mauzo yako, faida, na vidokezo kupitia WhatsApp.\n\n📱 ${assistantName} — Msaidizi wako wa Biashara`,
                sheng: `✅ Imeisha!\n\nPoa ${userName}! Sasa kila evening ${assistantName} atakutumia sales report, profit na tips kwa WhatsApp.\n\n📱 ${assistantName} — Boy wako wa Biashara 💪`,
                en: `✅ Connected!\n\nGreat ${userName}! Every evening ${assistantName} will send you a summary of your sales, profits, and tips via WhatsApp.\n\n📱 ${assistantName} — Your Business Assistant`
            };
            await client.sendText(phone, messages[language] || messages.sw);
            return { success: true };
        } catch (error) { console.error('[WhatsApp] Error sending confirmation:', error); return { success: false }; }
    }

    static async connectUser({ userId, phone, assistantName, language, reportTime }) {
        const connection = { id: uuidv4(), userId, phone, connected: true, connectedAt: new Date().toISOString(), assistantName, language, reportTime, lastReportSent: null, userName: null };
        connections.set(userId, connection);
        console.log(`[WhatsApp] Connected user ${userId} to ${phone}`);
        return connection;
    }

    static async getConnection(userId) { return connections.get(userId) || null; }
    static async disconnectUser(userId) { const c = connections.get(userId); if (c) { c.connected = false; connections.set(userId, c); } }
    static async updateLastReportSent(userId) { const c = connections.get(userId); if (c) { c.lastReportSent = new Date().toISOString(); connections.set(userId, c); } }

    static async generateReport({ userId, reportType, date, assistantName, userName, language }) {
        const generator = new ReportGenerator();
        return await generator.generate({ userId, reportType, date, assistantName, userName, language });
    }

    static async sendReport({ phone, report }) {
        try {
            const client = OpenWAClient.getInstance();
            const result = await client.sendText(phone, report);
            if (result && result.id) { console.log(`[WhatsApp] Report sent to ${phone}`); return { success: true, messageId: result.id._serialized }; }
            return { success: false };
        } catch (error) { console.error('[WhatsApp] Error sending report:', error); return { success: false }; }
    }

    static async getAllConnectedUsers() {
        const connected = [];
        for (const [userId, connection] of connections) { if (connection.connected) connected.push(connection); }
        return connected;
    }

    static async getUsersForReportTime(reportTime) {
        const allUsers = await this.getAllConnectedUsers();
        return allUsers.filter(u => u.reportTime === reportTime);
    }

    static async updateReportPreference(userId, enabled) { const c = connections.get(userId); if (c) { c.reportsEnabled = enabled; connections.set(userId, c); } }
    static async updateLanguage(userId, language) { const c = connections.get(userId); if (c) { c.language = language; connections.set(userId, c); } }
    static async findVerificationByMessageId(messageId) { for (const [, v] of verifications) { if (v.messageId === messageId) return v; } return null; }
    static async markVerificationDelivered(verificationId) { const v = verifications.get(verificationId); if (v) { v.status = 'delivered'; verifications.set(verificationId, v); } }
}

module.exports = WhatsAppService;
