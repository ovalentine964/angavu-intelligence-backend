const express = require('express');
const router = express.Router();
const rateLimit = require('express-rate-limit');
const WhatsAppService = require('../services/WhatsAppService');

const connectLimiter = rateLimit({ windowMs: 60000, max: 5, message: { status: 'error', error_code: 'RATE_LIMIT', message: 'Umeomba mara nyingi sana. Tafadhali subiri.' } });
const verifyLimiter = rateLimit({ windowMs: 60000, max: 10, message: { status: 'error', error_code: 'RATE_LIMIT', message: 'Umeomba mara nyingi sana.' } });

router.post('/connect', connectLimiter, async (req, res) => {
    try {
        const { phone, user_id, name, assistant_name, language, report_time } = req.body;
        if (!phone || !user_id || !name) return res.status(400).json({ status: 'error', error_code: 'MISSING_FIELDS', message: 'Tafadhali jaza namba ya simu, jina, na user ID.' });
        if (!/^\+254[17]\d{8}$/.test(phone)) return res.status(400).json({ status: 'error', error_code: 'INVALID_PHONE', message: 'Namba ya simu si sahihi.' });

        const existing = await WhatsAppService.getConnection(user_id);
        if (existing && existing.connected) return res.json({ status: 'already_connected', verification_id: existing.whatsapp_id, message: 'Namba hii tayari imeunganishwa.' });

        const isOnWhatsApp = await WhatsAppService.checkNumberOnWhatsApp(phone);
        if (!isOnWhatsApp) return res.json({ status: 'error', error_code: 'NUMBER_NOT_ON_WHATSAPP', message: 'Namba hii haiko kwenye WhatsApp.' });

        const verification = await WhatsAppService.createVerification({ phone, userId: user_id, userName: name, assistantName: assistant_name || 'Msaidizi', language: language || 'sw', reportTime: report_time || 'evening' });
        const messageResult = await WhatsAppService.sendVerificationMessage({ phone, verificationId: verification.id, userName: name, assistantName: assistant_name || 'Msaidizi', language: language || 'sw' });

        if (!messageResult.success) {
            if (messageResult.error === 'NOT_ON_WHATSAPP') return res.json({ status: 'error', error_code: 'NUMBER_NOT_ON_WHATSAPP', message: 'Namba hii haiko kwenye WhatsApp.' });
            return res.status(500).json({ status: 'error', error_code: 'SEND_FAILED', message: 'Imeshindwa kutuma ujumbe.' });
        }

        res.json({ status: 'sent', verification_id: verification.id, message: 'Ujumbe wa WhatsApp umetumwa.' });
    } catch (error) {
        console.error('WhatsApp connect error:', error);
        res.status(500).json({ status: 'error', error_code: 'INTERNAL_ERROR', message: 'Kuna tatzo la ndani.' });
    }
});

router.post('/verify', verifyLimiter, async (req, res) => {
    try {
        const { verification_id, code } = req.body;
        if (!verification_id) return res.status(400).json({ status: 'error', message: 'Tafadhali jaza verification ID.' });

        const verification = await WhatsAppService.getVerification(verification_id);
        if (!verification) return res.json({ status: 'expired', message: 'Muda umekwisha.' });

        const age = Date.now() - verification.createdAt;
        if (age > 5 * 60 * 1000) { await WhatsAppService.markVerificationExpired(verification_id); return res.json({ status: 'expired', message: 'Muda umekwisha.' }); }

        if (code && verification.code !== code) return res.json({ status: 'error', message: 'Msimbo si sahihi.' });

        const connection = await WhatsAppService.connectUser({ userId: verification.userId, phone: verification.phone, assistantName: verification.assistantName, language: verification.language, reportTime: verification.reportTime });
        await WhatsAppService.sendConfirmationMessage({ phone: verification.phone, userName: verification.userName, assistantName: verification.assistantName, language: verification.language });

        res.json({ status: 'connected', whatsapp_id: connection.id, message: 'WhatsApp imeunganishwa!' });
    } catch (error) {
        console.error('WhatsApp verify error:', error);
        res.status(500).json({ status: 'error', message: 'Kuna tatzo.' });
    }
});

router.get('/verify/:verificationId/status', async (req, res) => {
    try {
        const verification = await WhatsAppService.getVerification(req.params.verificationId);
        if (!verification) return res.json({ status: 'expired', message: 'Muda umekwisha.' });
        if (verification.status === 'connected') return res.json({ status: 'connected', whatsapp_id: verification.whatsappId, message: 'WhatsApp imeunganishwa!' });
        const age = Date.now() - verification.createdAt;
        if (age > 5 * 60 * 1000) { await WhatsAppService.markVerificationExpired(req.params.verificationId); return res.json({ status: 'expired', message: 'Muda umekwisha.' }); }
        res.json({ status: 'pending', message: 'Bado nasubiri...' });
    } catch (error) {
        console.error('Verification status error:', error);
        res.status(500).json({ status: 'error', message: 'Kuna tatzo.' });
    }
});

router.get('/connection/:userId', async (req, res) => {
    try {
        const connection = await WhatsAppService.getConnection(req.params.userId);
        if (!connection) return res.json({ user_id: req.params.userId, phone: null, connected: false });
        res.json({ user_id: req.params.userId, phone: connection.phone, connected: connection.connected, connected_at: connection.connectedAt, assistant_name: connection.assistantName, language: connection.language, report_time: connection.reportTime, last_report_sent: connection.lastReportSent });
    } catch (error) {
        console.error('Get connection error:', error);
        res.status(500).json({ status: 'error', message: 'Kuna tatzo.' });
    }
});

router.post('/disconnect/:userId', async (req, res) => {
    try {
        await WhatsAppService.disconnectUser(req.params.userId);
        res.json({ status: 'disconnected', message: 'WhatsApp imeondolewa.' });
    } catch (error) {
        console.error('Disconnect error:', error);
        res.status(500).json({ status: 'error', message: 'Kuna tatzo.' });
    }
});

router.post('/send-report', async (req, res) => {
    try {
        const { user_id, report_type, date } = req.body;
        if (!user_id || !report_type) return res.status(400).json({ status: 'error', message: 'Tafadhali jaza user_id na report_type.' });

        const connection = await WhatsAppService.getConnection(user_id);
        if (!connection || !connection.connected) return res.json({ status: 'error', message: 'Mtumiaji hajaunganisha WhatsApp.' });

        const report = await WhatsAppService.generateReport({ userId: user_id, reportType: report_type, date: date || new Date().toISOString().split('T')[0], assistantName: connection.assistantName, userName: connection.userName, language: connection.language });
        const result = await WhatsAppService.sendReport({ phone: connection.phone, report, language: connection.language });

        if (result.success) {
            await WhatsAppService.updateLastReportSent(user_id);
            res.json({ status: 'sent', message_id: result.messageId, message: 'Ripoti imetumwa.' });
        } else {
            res.status(500).json({ status: 'error', message: 'Imeshindwa kutuma ripoti.' });
        }
    } catch (error) {
        console.error('Send report error:', error);
        res.status(500).json({ status: 'error', message: 'Kuna tatzo.' });
    }
});

module.exports = router;
