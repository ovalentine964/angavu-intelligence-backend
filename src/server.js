/**
 * Msaidizi Backend Server
 * 
 * Main entry point for the Msaidizi business assistant backend.
 * 
 * Features:
 *  - WhatsApp connection management
 *  - Report generation and delivery
 *  - User management
 *  - OpenWA integration
 *  - REST API endpoints
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
const { initializeOpenWA } = require('./openwa');

// Import routes
const whatsappRoutes = require('./routes/whatsapp');

// Create Express app
const app = express();

// ── Middleware ──────────────────────────────────────────────────────────────

// Security headers
app.use(helmet());

// CORS
app.use(cors({
    origin: process.env.ALLOWED_ORIGINS ? process.env.ALLOWED_ORIGINS.split(',') : '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: true
}));

// Request logging
app.use(morgan('combined'));

// Body parsing
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Global rate limiting
const globalLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 100, // 100 requests per 15 minutes
    message: {
        status: 'error',
        message: 'Too many requests. Please try again later.'
    }
});
app.use(globalLimiter);

// ── Routes ─────────────────────────────────────────────────────────────────

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        uptime: process.uptime()
    });
});

// API routes
app.use('/api/v1/whatsapp', whatsappRoutes);

// Welcome message
app.get('/', (req, res) => {
    res.json({
        name: 'Msaidizi Business Assistant API',
        version: '1.0.0',
        description: 'Backend API for Msaidizi WhatsApp business assistant',
        endpoints: {
            health: '/health',
            whatsapp: '/api/v1/whatsapp'
        }
    });
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({
        status: 'error',
        message: 'Route not found'
    });
});

// Error handler
app.use((err, req, res, next) => {
    console.error('Unhandled error:', err);

    res.status(err.status || 500).json({
        status: 'error',
        message: process.env.NODE_ENV === 'production'
            ? 'Internal server error'
            : err.message
    });
});

// ── Server Startup ─────────────────────────────────────────────────────────

const PORT = process.env.PORT || 3000;

async function startServer() {
    try {
        console.log('[Server] Starting Msaidizi Backend...');

        // Initialize OpenWA integration
        console.log('[Server] Initializing OpenWA integration...');
        try {
            await initializeOpenWA();
            console.log('[Server] OpenWA integration initialized');
        } catch (error) {
            console.error('[Server] OpenWA initialization failed:', error.message);
            console.log('[Server] Continuing without OpenWA (WhatsApp features disabled)');
        }

        // Start Express server
        const server = app.listen(PORT, () => {
            console.log(`[Server] Msaidizi Backend running on port ${PORT}`);
            console.log(`[Server] Health check: http://localhost:${PORT}/health`);
            console.log(`[Server] API docs: http://localhost:${PORT}/`);
        });

        // Graceful shutdown
        const shutdown = async (signal) => {
            console.log(`\n[Server] Received ${signal}, shutting down gracefully...`);

            // Close HTTP server
            server.close(() => {
                console.log('[Server] HTTP server closed');
            });

            // Close OpenWA integration
            try {
                const { getOpenWAIntegration } = require('./openwa');
                const openwa = getOpenWAIntegration();
                await openwa.shutdown();
            } catch (error) {
                console.error('[Server] Error shutting down OpenWA:', error.message);
            }

            console.log('[Server] Shutdown complete');
            process.exit(0);
        };

        process.on('SIGTERM', () => shutdown('SIGTERM'));
        process.on('SIGINT', () => shutdown('SIGINT'));

        // Handle uncaught exceptions
        process.on('uncaughtException', (error) => {
            console.error('[Server] Uncaught exception:', error);
            // Don't exit in production, just log
            if (process.env.NODE_ENV !== 'production') {
                process.exit(1);
            }
        });

        process.on('unhandledRejection', (reason, promise) => {
            console.error('[Server] Unhandled rejection at:', promise, 'reason:', reason);
        });

    } catch (error) {
        console.error('[Server] Failed to start:', error);
        process.exit(1);
    }
}

// Start the server
startServer();

module.exports = app;
