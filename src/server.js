const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
const { initializeOpenWA } = require('./openwa');

const whatsappRoutes = require('./routes/whatsapp');

const app = express();

app.use(helmet());
app.use(cors({ origin: process.env.ALLOWED_ORIGINS ? process.env.ALLOWED_ORIGINS.split(',') : '*', methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allowedHeaders: ['Content-Type', 'Authorization'], credentials: true }));
app.use(morgan('combined'));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100, message: { status: 'error', message: 'Too many requests.' } }));

app.get('/health', (req, res) => res.json({ status: 'healthy', timestamp: new Date().toISOString(), uptime: process.uptime() }));
app.use('/api/v1/whatsapp', whatsappRoutes);
app.get('/', (req, res) => res.json({ name: 'Msaidizi Business Assistant API', version: '1.0.0', endpoints: { health: '/health', whatsapp: '/api/v1/whatsapp' } }));
app.use((req, res) => res.status(404).json({ status: 'error', message: 'Route not found' }));
app.use((err, req, res, next) => { console.error('Unhandled error:', err); res.status(err.status || 500).json({ status: 'error', message: process.env.NODE_ENV === 'production' ? 'Internal server error' : err.message }); });

const PORT = process.env.PORT || 3000;

async function startServer() {
    try {
        console.log('[Server] Starting Msaidizi Backend...');
        try { await initializeOpenWA(); console.log('[Server] OpenWA initialized'); } catch (error) { console.error('[Server] OpenWA failed:', error.message); console.log('[Server] Continuing without OpenWA'); }

        const server = app.listen(PORT, () => {
            console.log(`[Server] Msaidizi Backend running on port ${PORT}`);
            console.log(`[Server] Health: http://localhost:${PORT}/health`);
        });

        const shutdown = async (signal) => {
            console.log(`\n[Server] ${signal} received, shutting down...`);
            server.close(() => console.log('[Server] HTTP server closed'));
            try { const { getOpenWAIntegration } = require('./openwa'); await getOpenWAIntegration().shutdown(); } catch (error) {}
            console.log('[Server] Shutdown complete');
            process.exit(0);
        };

        process.on('SIGTERM', () => shutdown('SIGTERM'));
        process.on('SIGINT', () => shutdown('SIGINT'));
        process.on('uncaughtException', (error) => { console.error('[Server] Uncaught:', error); if (process.env.NODE_ENV !== 'production') process.exit(1); });
        process.on('unhandledRejection', (reason) => console.error('[Server] Unhandled rejection:', reason));
    } catch (error) { console.error('[Server] Failed to start:', error); process.exit(1); }
}

startServer();
module.exports = app;
