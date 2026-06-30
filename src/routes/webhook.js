/**
 * OpenWA Webhook Handler
 * 
 * Handles incoming webhooks from OpenWA for message delivery receipts
 * and other events.
 */

const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const WhatsAppService = require('../services/WhatsAppService');

// Webhook secret for verification
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || 'msaidizi-webhook-secret';

/**
 * Verify webhook signature
 */
function verifySignature(req, res, next) {
    const signature = req.headers['x-webhook-signature'];
    
    if (!signature) {
        console.warn('[Webhook] No signature provided');
        // In development, allow without signature
        if (process.env.NODE_ENV === 'development') {
            return next();
        }
        return res.status(401).json({ error: 'No signature' });
    }

    const payload = JSON.stringify(req.body);
    const expectedSignature = crypto
        .createHmac('sha256', WEBHOOK_SECRET)
        .update(payload)
        .digest('hex');

    if (signature !== expectedSignature) {
        console.warn('[Webhook] Invalid signature');
        return res.status(401).json({ error: 'Invalid signature' });
    }

    next();
}

/**
 * POST /webhook/message
 * 
 * Handle incoming message webhook from OpenWA
 */
router.post('/message', verifySignature, async (req, res) => {
    try {
        const { event, data } = req.body;

        console.log(`[Webhook] Received ${event} event`);

        if (event === 'message') {
            await handleMessageWebhook(data);
        } else if (event === 'message.any') {
            await handleAnyMessageWebhook(data);
        }

        res.json({ status: 'ok' });

    } catch (error) {
        console.error('[Webhook] Error handling message:', error);
        res.status(500).json({ error: 'Internal error' });
    }
});

/**
 * POST /webhook/receipt
 * 
 * Handle delivery receipt webhook from OpenWA
 */
router.post('/receipt', verifySignature, async (req, res) => {
    try {
        const { event, data } = req.body;

        console.log(`[Webhook] Received ${event} receipt`);

        if (event === 'message.receipt' || event === 'message.ack') {
            await handleReceiptWebhook(data);
        }

        res.json({ status: 'ok' });

    } catch (error) {
        console.error('[Webhook] Error handling receipt:', error);
        res.status(500).json({ error: 'Internal error' });
    }
});

/**
 * POST /webhook/state
 * 
 * Handle state change webhook from OpenWA
 */
router.post('/state', verifySignature, async (req, res) => {
    try {
        const { event, data } = req.body;

        console.log(`[Webhook] State changed: ${data.state}`);

        if (data.state === 'DISCONNECTED') {
            console.error('[Webhook] WhatsApp disconnected!');
            // Could trigger alerting here
        }

        res.json({ status: 'ok' });

    } catch (error) {
        console.error('[Webhook] Error handling state:', error);
        res.status(500).json({ error: 'Internal error' });
    }
});

/**
 * Handle incoming message webhook
 */
async function handleMessageWebhook(data) {
    const { from, body, id, timestamp } = data;

    console.log(`[Webhook] Message from ${from}: ${body}`);

    // Log message to database
    await logMessage({
        direction: 'inbound',
        from,
        body,
        messageId: id,
        timestamp
    });
}

/**
 * Handle any message webhook (includes status broadcasts)
 */
async function handleAnyMessageWebhook(data) {
    // Filter out status broadcasts
    if (data.from === 'status@broadcast') {
        return;
    }

    console.log(`[Webhook] Any message from ${data.from}`);
}

/**
 * Handle delivery receipt webhook
 */
async function handleReceiptWebhook(data) {
    const { id, to, ack, timestamp } = data;

    // ack values:
    // 0 = PENDING
    // 1 = SERVER
    // 2 = DEVICE (delivered)
    // 3 = READ
    // 4 = PLAYED

    const statusMap = {
        0: 'pending',
        1: 'sent',
        2: 'delivered',
        3: 'read',
        4: 'played'
    };

    const status = statusMap[ack] || 'unknown';

    console.log(`[Webhook] Receipt for ${id}: ${status}`);

    // Update message status in database
    await updateMessageStatus(id, status);

    // If delivered, check if this is a verification message
    if (ack === 2) {
        await handleVerificationDelivery(id, to);
    }
}

/**
 * Handle verification message delivery
 */
async function handleVerificationDelivery(messageId, phone) {
    try {
        // Find verification by message ID
        const verification = await WhatsAppService.findVerificationByMessageId(messageId);
        
        if (verification && verification.status === 'pending') {
            console.log(`[Webhook] Verification ${verification.id} delivered to ${phone}`);
            
            // Auto-confirm verification on delivery
            await WhatsAppService.markVerificationDelivered(verification.id);
        }

    } catch (error) {
        console.error('[Webhook] Error handling verification delivery:', error);
    }
}

/**
 * Log message to database
 */
async function logMessage({ direction, from, body, messageId, timestamp }) {
    // TODO: Implement database logging
    console.log(`[Webhook] Logging ${direction} message: ${messageId}`);
}

/**
 * Update message status in database
 */
async function updateMessageStatus(messageId, status) {
    // TODO: Implement database update
    console.log(`[Webhook] Updating message ${messageId} status to ${status}`);
}

module.exports = router;
