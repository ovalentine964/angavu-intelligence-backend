/**
 * OpenWA Configuration
 * 
 * Configuration for OpenWA WhatsApp gateway.
 * This file contains all the settings for the OpenWA integration.
 */

module.exports = {
    // Server configuration
    server: {
        port: process.env.OPENWA_PORT || 8080,
        host: process.env.OPENWA_HOST || '0.0.0.0',
        api_key: process.env.OPENWA_API_KEY || '',
    },

    // Session configuration
    session: {
        id: process.env.OPENWA_SESSION_ID || 'msaidizi',
        data_path: process.env.OPENWA_DATA_PATH || './session-data',
        multi_device: true,
        auth_timeout: 60, // seconds
        qr_timeout: 0, // no timeout
    },

    // WhatsApp configuration
    whatsapp: {
        // Maximum message length
        max_message_length: 65536,

        // Rate limiting
        rate_limit: {
            messages_per_second: 10,
            messages_per_minute: 100,
            messages_per_hour: 1000,
        },

        // Retry configuration
        retry: {
            max_attempts: 3,
            delay_ms: 1000,
            backoff_multiplier: 2,
        },

        // Message types
        message_types: {
            text: 'text',
            image: 'image',
            document: 'document',
            audio: 'audio',
            video: 'video',
            location: 'location',
            contact: 'contact',
        },
    },

    // Report configuration
    reports: {
        // Schedule (EAT timezone)
        schedule: {
            morning: '0 8 * * *',    // 8:00 AM
            afternoon: '0 13 * * *', // 1:00 PM
            evening: '0 18 * * *',   // 6:00 PM
            weekly: '0 18 * * 0',    // Sunday 6:00 PM
        },

        // Report templates
        templates: {
            daily: {
                sw: 'ripoti_ya_leo',
                sheng: 'report_ya_leo',
                en: 'daily_report',
            },
            weekly: {
                sw: 'ripoti_ya_wiki',
                sheng: 'report_ya_wiki',
                en: 'weekly_report',
            },
        },

        // Maximum report length
        max_length: 4096,
    },

    // Command configuration
    commands: {
        // Command patterns (case-insensitive)
        patterns: {
            report: /^(ripoti|report|leo|today)$/i,
            sales: /^(mauzo|sales|sold)$/i,
            profit: /^(faida|profit|mapato)$/i,
            weekly: /^(wiki|weekly|week)$/i,
            help: /^(msaada|help|sos|menu)$/i,
            share: /^(shiriki|share|tuma|send)$/i,
            stop: /^(simama|stop|cancel|ondoa)$/i,
            start: /^(anza|start|subscribe|jiunge)$/i,
            swahili: /^(sw|swahili|kiswahili)$/i,
            sheng: /^(sheng|sh)$/i,
            english: /^(en|english|kingereza)$/i,
            status: /^(hali|status|state)$/i,
        },

        // Response templates
        responses: {
            unknown: {
                sw: '🤔 Sijaelewa.\n\nTuma "msaada" kuona amri zote.',
                sheng: '🤔 Sijaelewa boss.\n\nTuma "msaada" kuona commands zote.',
                en: '🤔 I didn\'t understand.\n\nSend "help" to see all commands.',
            },
        },
    },

    // Logging configuration
    logging: {
        level: process.env.LOG_LEVEL || 'info',
        file: process.env.LOG_FILE || 'logs/openwa.log',
        max_size: '10m',
        max_files: 5,
    },

    // Feature flags
    features: {
        media_messages: true,
        location_messages: true,
        contact_messages: true,
        group_messages: false, // Disable group messages for now
        broadcast: false, // Disable broadcast for now
        analytics: false, // Disable analytics for now
    },

    // Security
    security: {
        // Allowed phone numbers (empty = allow all)
        allowed_numbers: [],

        // Blocked phone numbers
        blocked_numbers: [],

        // Maximum message size (bytes)
        max_message_size: 1024 * 1024, // 1MB

        // Rate limiting per user
        user_rate_limit: {
            messages_per_minute: 20,
            messages_per_hour: 100,
        },
    },

    // Webhook configuration
    webhooks: {
        // Incoming message webhook
        message: {
            url: process.env.WEBHOOK_MESSAGE_URL || '',
            secret: process.env.WEBHOOK_SECRET || '',
        },

        // Delivery receipt webhook
        receipt: {
            url: process.env.WEBHOOK_RECEIPT_URL || '',
            secret: process.env.WEBHOOK_SECRET || '',
        },
    },
};
