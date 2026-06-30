const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const WhatsAppService = require('../services/WhatsAppService');

const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || 'msaidizi-webhook-secret';

function verifySignature(req, res, next) {
    const signature = req.headers['x-webhook-signature'];
    if (!signature) { if (process.env.NODE_ENV === 'development') return next(); return res.status(401).json({ error: 'No signature' }); }
    const payload = JSON.stringify(req.body);
    const expectedSignature = crypto.createHmac('sha256', WEBHOOK_SECRET).update(payload).digest('hex');
    if (signature !== expectedSignature) return res.status(401).json({ error: 'Invalid signature' });
    next();
}

router.post('/message', verifySignature, async (req, res) => {
    try {
        const { event, data } = req.body;
        console.log(`[Webhook] Received ${event} event`);
        if (event === 'message') await handleMessageWebhook(data);
        res.json({ status: 'ok' });
    } catch (error) { console.error('[Webhook] Error:', error); res.status(500).json({ error: 'Internal error' }); }
});

router.post('/receipt', verifySignature, async (req, res) => {
    try {
        const { event, data } = req.body;
        console.log(`[Webhook] Received ${event} receipt`);
        if (event === 'message.receipt' || event === 'message.ack') await handleReceiptWebhook(data);
        res.json({ status: 'ok' });
    } catch (error) { console.error('[Webhook] Error:', error); res.status(500).json({ error: 'Internal error' }); }
});

router.post('/state', verifySignature, async (req, res) => {
    try {
        const { data } = req.body;
        console.log(`[Webhook] State: ${data.state}`);
        if (data.state === 'DISCONNECTED') console.error('[Webhook] WhatsApp disconnected!');
        res.json({ status: 'ok' });
    } catch (error) { console.error('[Webhook] Error:', error); res.status(500).json({ error: 'Internal error' }); }
});

async function handleMessageWebhook(data) {
    const { from, body, id } = data;
    console.log(`[Webhook] Message from ${from}: ${body}`);
}

async function handleReceiptWebhook(data) {
    const { id, to, ack } = data;
    const statusMap = { 0: 'pending', 1: 'sent', 2: 'delivered', 3: 'read', 4: 'played' };
    const status = statusMap[ack] || 'unknown';
    console.log(`[Webhook] Receipt for ${id}: ${status}`);
    if (ack === 2) {
        const verification = await WhatsAppService.findVerificationByMessageId(id);
        if (verification && verification.status === 'pending') await WhatsAppService.markVerificationDelivered(verification.id);
    }
}

module.exports = router;
