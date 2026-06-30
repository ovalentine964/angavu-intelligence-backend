/**
 * Verification Model
 * 
 * Represents a WhatsApp verification record.
 * In production, this would be stored in a database (MongoDB, PostgreSQL, etc.).
 */

const { v4: uuidv4 } = require('uuid');

class Verification {
    /**
     * Create a new verification record.
     */
    static create({ phone, userId, userName, assistantName, language, reportTime }) {
        return {
            id: uuidv4(),
            phone,
            userId,
            userName,
            assistantName,
            language: language || 'sw',
            reportTime: reportTime || 'evening',
            code: Math.random().toString().slice(2, 6), // 4-digit code
            status: 'pending', // pending, connected, expired
            createdAt: Date.now(),
            connectedAt: null,
            whatsappId: null,
            deliveryReceiptReceived: false,
            attempts: 0,
            lastAttemptAt: null
        };
    }

    /**
     * Check if verification is expired (5 minutes).
     */
    static isExpired(verification) {
        const maxAge = 5 * 60 * 1000; // 5 minutes
        return (Date.now() - verification.createdAt) > maxAge;
    }

    /**
     * Mark verification as connected.
     */
    static markConnected(verification, whatsappId) {
        return {
            ...verification,
            status: 'connected',
            connectedAt: Date.now(),
            whatsappId: whatsappId || null
        };
    }

    /**
     * Mark verification as expired.
     */
    static markExpired(verification) {
        return {
            ...verification,
            status: 'expired'
        };
    }

    /**
     * Increment attempt counter.
     */
    static incrementAttempt(verification) {
        return {
            ...verification,
            attempts: verification.attempts + 1,
            lastAttemptAt: Date.now()
        };
    }

    /**
     * Mark delivery receipt received.
     */
    static markDeliveryReceipt(verification) {
        return {
            ...verification,
            deliveryReceiptReceived: true
        };
    }

    /**
     * Verify code.
     */
    static verifyCode(verification, code) {
        return verification.code === code;
    }

    /**
     * Get verification summary for logging.
     */
    static getSummary(verification) {
        return {
            id: verification.id,
            phone: verification.phone.replace(/(\d{4})\d{4}(\d{3})/, '$1****$2'),
            userId: verification.userId,
            status: verification.status,
            age: Date.now() - verification.createdAt
        };
    }
}

module.exports = Verification;
