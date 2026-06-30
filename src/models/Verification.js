const { v4: uuidv4 } = require('uuid');

class Verification {
    static create({ phone, userId, userName, assistantName, language, reportTime }) {
        return {
            id: uuidv4(),
            phone,
            userId,
            userName,
            assistantName,
            language: language || 'sw',
            reportTime: reportTime || 'evening',
            code: Math.random().toString().slice(2, 6),
            status: 'pending',
            createdAt: Date.now(),
            connectedAt: null,
            whatsappId: null,
            deliveryReceiptReceived: false,
            attempts: 0,
            lastAttemptAt: null
        };
    }

    static isExpired(verification) {
        return (Date.now() - verification.createdAt) > 5 * 60 * 1000;
    }

    static markConnected(verification, whatsappId) {
        return { ...verification, status: 'connected', connectedAt: Date.now(), whatsappId: whatsappId || null };
    }

    static markExpired(verification) {
        return { ...verification, status: 'expired' };
    }

    static incrementAttempt(verification) {
        return { ...verification, attempts: verification.attempts + 1, lastAttemptAt: Date.now() };
    }

    static markDeliveryReceipt(verification) {
        return { ...verification, deliveryReceiptReceived: true };
    }

    static verifyCode(verification, code) {
        return verification.code === code;
    }

    static getSummary(verification) {
        return { id: verification.id, phone: verification.phone.replace(/(\d{4})\d{4}(\d{3})/, '$1****$2'), userId: verification.userId, status: verification.status, age: Date.now() - verification.createdAt };
    }
}

module.exports = Verification;
