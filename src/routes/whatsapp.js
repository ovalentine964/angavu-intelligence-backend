/**
 * WhatsApp Connection Routes
 * 
 * POST /api/v1/whatsapp/connect    — Initiate WhatsApp connection
 * POST /api/v1/whatsapp/verify     — Confirm verification
 * GET  /api/v1/whatsapp/verify/:id/status — Poll verification status
 * GET  /api/v1/whatsapp/connection/:userId — Get connection state
 * POST /api/v1/whatsapp/disconnect/:userId — Disconnect WhatsApp
 * POST /api/v1/whatsapp/send-report — Send report via WhatsApp
 */

const express = require('express');
const router = express.Router();
const { body, param, validationResult } = require('express-rate-limit');
const rateLimit = require('express-rate-limit');
const WhatsAppService = require('../services/WhatsAppService');
const { authenticate } = require('../middleware/auth');

// Rate limiting for connect endpoint (prevent abuse)
const connectLimiter = rateLimit({
    windowMs: 60 * 1000, // 1 minute
    max: 5, // 5 attempts per minute per IP
    message: {
        status: 'error',
        error_code: 'RATE_LIMIT',
        message: 'Umeomba mara nyingi sana. Tafadhali subiri dakika chache.'
    }
});

// Rate limiting for verify endpoint
const verifyLimiter = rateLimit({
    windowMs: 60 * 1000,
    max: 10,
    message: {
        status: 'error',
        error_code: 'RATE_LIMIT',
        message: 'Umeomba mara nyingi sana. Tafadhali subiri.'
    }
});

/**
 * POST /api/v1/whatsapp/connect
 * 
 * Initiate WhatsApp connection during onboarding.
 * Sends a verification/welcome message to the provided phone number via OpenWA.
 * 
 * Body:
 *   - phone: "+254712345678" (normalized Kenyan number)
 *   - user_id: string
 *   - name: string (worker's name, e.g. "Valentine")
 *   - assistant_name: string (what they named Msaidizi, e.g. "Simba")
 *   - language: string ("sw", "sheng", "en")
 *   - report_time: string ("morning", "afternoon", "evening")
 */
router.post('/connect', connectLimiter, async (req, res) => {
    try {
        const { phone, user_id, name, assistant_name, language, report_time } = req.body;

        // Validate required fields
        if (!phone || !user_id || !name) {
            return res.status(400).json({
                status: 'error',
                error_code: 'MISSING_FIELDS',
                message: 'Tafadhali jaza namba ya simu, jina, na user ID.'
            });
        }

        // Validate phone format
        if (!/^\+254[17]\d{8}$/.test(phone)) {
            return res.status(400).json({
                status: 'error',
                error_code: 'INVALID_PHONE',
                message: 'Namba ya simu si sahihi. Tafadhali weka namba ya Kenya (mfano: 0712345678).'
            });
        }

        // Check if already connected
        const existingConnection = await WhatsAppService.getConnection(user_id);
        if (existingConnection && existingConnection.connected) {
            return res.json({
                status: 'already_connected',
                verification_id: existingConnection.whatsapp_id,
                message: 'Namba hii tayari imeunganishwa na WhatsApp.'
            });
        }

        // Check if number is on WhatsApp
        const isOnWhatsApp = await WhatsAppService.checkNumberOnWhatsApp(phone);
        if (!isOnWhatsApp) {
            return res.json({
                status: 'error',
                error_code: 'NUMBER_NOT_ON_WHATSAPP',
                message: 'Namba hii haiko kwenye WhatsApp. Tafadhali hakikisha una WhatsApp imewashwa.'
            });
        }

        // Create verification record
        const verification = await WhatsAppService.createVerification({
            phone,
            userId: user_id,
            userName: name,
            assistantName: assistant_name || 'Msaidizi',
            language: language || 'sw',
            reportTime: report_time || 'evening'
        });

        // Send welcome/verification message via OpenWA
        const messageResult = await WhatsAppService.sendVerificationMessage({
            phone,
            verificationId: verification.id,
            userName: name,
            assistantName: assistant_name || 'Msaidizi',
            language: language || 'sw'
        });

        if (!messageResult.success) {
            // Handle specific OpenWA errors
            if (messageResult.error === 'NOT_ON_WHATSAPP') {
                return res.json({
                    status: 'error',
                    error_code: 'NUMBER_NOT_ON_WHATSAPP',
                    message: 'Namba hii haiko kwenye WhatsApp.'
                });
            }

            return res.status(500).json({
                status: 'error',
                error_code: 'SEND_FAILED',
                message: 'Imeshindwa kutuma ujumbe wa WhatsApp. Tafadhali jaribu tena.'
            });
        }

        // Return verification ID for polling
        res.json({
            status: 'sent',
            verification_id: verification.id,
            message: 'Ujumbe wa WhatsApp umetumwa. Angalia WhatsApp yako.'
        });

    } catch (error) {
        console.error('WhatsApp connect error:', error);
        res.status(500).json({
            status: 'error',
            error_code: 'INTERNAL_ERROR',
            message: 'Kuna tatzo la ndani. Tafadhali jaribu tena.'
        });
    }
});

/**
 * POST /api/v1/whatsapp/verify
 * 
 * Confirm WhatsApp connection.
 * Can be called:
 *   - With a code (if user enters a verification code)
 *   - Without a code (auto-confirm on delivery receipt)
 * 
 * Body:
 *   - verification_id: string
 *   - code: string (optional)
 */
router.post('/verify', verifyLimiter, async (req, res) => {
    try {
        const { verification_id, code } = req.body;

        if (!verification_id) {
            return res.status(400).json({
                status: 'error',
                message: 'Tafadhali jaza verification ID.'
            });
        }

        // Get verification record
        const verification = await WhatsAppService.getVerification(verification_id);
        if (!verification) {
            return res.json({
                status: 'expired',
                message: 'Muda wa uthibitisho umekwisha. Tafadhali jaribu tena.'
            });
        }

        // Check if expired (5 minutes)
        const age = Date.now() - verification.createdAt;
        if (age > 5 * 60 * 1000) {
            await WhatsAppService.markVerificationExpired(verification_id);
            return res.json({
                status: 'expired',
                message: 'Muda wa uthibitisho umekwisha.'
            });
        }

        // If code provided, verify it
        if (code && verification.code !== code) {
            return res.json({
                status: 'error',
                message: 'Msimbo si sahihi. Tafadhali jaribu tena.'
            });
        }

        // Mark as connected
        const connection = await WhatsAppService.connectUser({
            userId: verification.userId,
            phone: verification.phone,
            assistantName: verification.assistantName,
            language: verification.language,
            reportTime: verification.reportTime
        });

        // Send confirmation message
        await WhatsAppService.sendConfirmationMessage({
            phone: verification.phone,
            userName: verification.userName,
            assistantName: verification.assistantName,
            language: verification.language
        });

        res.json({
            status: 'connected',
            whatsapp_id: connection.id,
            message: 'WhatsApp imeunganishwa!'
        });

    } catch (error) {
        console.error('WhatsApp verify error:', error);
        res.status(500).json({
            status: 'error',
            message: 'Kuna tatzo. Tafadhali jaribu tena.'
        });
    }
});

/**
 * GET /api/v1/whatsapp/verify/:verificationId/status
 * 
 * Poll verification status.
 * Returns current state: pending, connected, expired.
 */
router.get('/verify/:verificationId/status', async (req, res) => {
    try {
        const { verificationId } = req.params;

        const verification = await WhatsAppService.getVerification(verificationId);
        if (!verification) {
            return res.json({
                status: 'expired',
                message: 'Muda umekwisha.'
            });
        }

        // Check if delivery was confirmed
        if (verification.status === 'connected') {
            return res.json({
                status: 'connected',
                whatsapp_id: verification.whatsappId,
                message: 'WhatsApp imeunganishwa!'
            });
        }

        // Check if expired
        const age = Date.now() - verification.createdAt;
        if (age > 5 * 60 * 1000) {
            await WhatsAppService.markVerificationExpired(verificationId);
            return res.json({
                status: 'expired',
                message: 'Muda umekwisha.'
            });
        }

        // Still pending
        res.json({
            status: 'pending',
            message: 'Bado nasubiri uthibitisho...'
        });

    } catch (error) {
        console.error('Verification status error:', error);
        res.status(500).json({
            status: 'error',
            message: 'Kuna tatzo.'
        });
    }
});

/**
 * GET /api/v1/whatsapp/connection/:userId
 * 
 * Get current WhatsApp connection state for a user.
 */
router.get('/connection/:userId', authenticate, async (req, res) => {
    try {
        const { userId } = req.params;

        const connection = await WhatsAppService.getConnection(userId);
        if (!connection) {
            return res.json({
                user_id: userId,
                phone: null,
                connected: false,
                message: 'Hakuna muungano wa WhatsApp.'
            });
        }

        res.json({
            user_id: userId,
            phone: connection.phone,
            connected: connection.connected,
            connected_at: connection.connectedAt,
            assistant_name: connection.assistantName,
            language: connection.language,
            report_time: connection.reportTime,
            last_report_sent: connection.lastReportSent
        });

    } catch (error) {
        console.error('Get connection error:', error);
        res.status(500).json({
            status: 'error',
            message: 'Kuna tatzo.'
        });
    }
});

/**
 * POST /api/v1/whatsapp/disconnect/:userId
 * 
 * Disconnect WhatsApp from user account.
 */
router.post('/disconnect/:userId', authenticate, async (req, res) => {
    try {
        const { userId } = req.params;

        await WhatsAppService.disconnectUser(userId);

        res.json({
            status: 'disconnected',
            message: 'WhatsApp imeondolewa.'
        });

    } catch (error) {
        console.error('Disconnect error:', error);
        res.status(500).json({
            status: 'error',
            message: 'Kuna tatzo.'
        });
    }
});

/**
 * POST /api/v1/whatsapp/send-report
 * 
 * Trigger a report send via WhatsApp.
 * Can be called by cron job or manually.
 * 
 * Body:
 *   - user_id: string
 *   - report_type: "daily" | "weekly"
 *   - date: string (ISO date, optional, defaults to today)
 */
router.post('/send-report', authenticate, async (req, res) => {
    try {
        const { user_id, report_type, date } = req.body;

        if (!user_id || !report_type) {
            return res.status(400).json({
                status: 'error',
                message: 'Tafadhali jaza user_id na report_type.'
            });
        }

        // Get user's WhatsApp connection
        const connection = await WhatsAppService.getConnection(user_id);
        if (!connection || !connection.connected) {
            return res.json({
                status: 'error',
                message: 'Mtumiaji hajaunganisha WhatsApp.'
            });
        }

        // Generate report
        const report = await WhatsAppService.generateReport({
            userId: user_id,
            reportType: report_type,
            date: date || new Date().toISOString().split('T')[0],
            assistantName: connection.assistantName,
            userName: connection.userName,
            language: connection.language
        });

        // Send via WhatsApp
        const result = await WhatsAppService.sendReport({
            phone: connection.phone,
            report,
            language: connection.language
        });

        if (result.success) {
            // Update last report sent timestamp
            await WhatsAppService.updateLastReportSent(user_id);

            res.json({
                status: 'sent',
                message_id: result.messageId,
                message: 'Ripoti imetumwa kupitia WhatsApp.'
            });
        } else {
            res.status(500).json({
                status: 'error',
                message: 'Imeshindwa kutuma ripoti.'
            });
        }

    } catch (error) {
        console.error('Send report error:', error);
        res.status(500).json({
            status: 'error',
            message: 'Kuna tatzo.'
        });
    }
});

module.exports = router;
