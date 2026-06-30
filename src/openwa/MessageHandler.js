/**
 * OpenWA Message Handlers
 * 
 * Handles incoming WhatsApp messages and routes them to appropriate handlers.
 * 
 * Supported commands:
 *  - "ripoti" / "report" → Get today's report
 *  - "mauzo" / "sales" → Get sales summary
 *  - "faida" / "profit" → Get profit summary
 *  - "msaada" / "help" → Show help message
 *  - "shiriki" / "share" → Get share link
 *  - "simama" / "stop" → Unsubscribe from reports
 */

const WhatsAppService = require('../services/WhatsAppService');
const ReportGenerator = require('../services/ReportGenerator');
const OpenWAClient = require('./OpenWAClient');

class MessageHandler {
    constructor() {
        this.client = OpenWAClient.getInstance();
        this.reportGenerator = new ReportGenerator();

        // Command patterns (case-insensitive)
        this.commands = {
            // Report commands
            ripoti: /^(ripoti|report|leo|today)$/i,
            mauzo: /^(mauzo|sales|sold)$/i,
            faida: /^(faida|profit|mapato)$/i,
            wiki: /^(wiki|weekly|week)$/i,

            // Help commands
            msaada: /^(msaada|help|sos|menu)$/i,

            // Share commands
            shiriki: /^(shiriki|share|tuma|send)$/i,

            // Subscription commands
            simama: /^(simama|stop|cancel|ondoa)$/i,
            anza: /^(anza|start|subscribe|jiunge)$/i,

            // Language commands
            kiswahili: /^(sw|swahili|kiswahili)$/i,
            sheng: /^(sheng|sh)$/i,
            english: /^(en|english|kingereza)$/i,

            // Status commands
            hali: /^(hali|status|state)$/i
        };
    }

    /**
     * Handle an incoming WhatsApp message.
     * 
     * @param {Object} message - OpenWA message object
     * @param {string} message.from - Sender phone (254712345678@c.us)
     * @param {string} message.body - Message text
     * @param {string} message.id - Message ID
     * @returns {Promise<void>}
     */
    async handleMessage(message) {
        try {
            const { from, body, id } = message;

            // Extract phone number from OpenWA format
            const phone = this.extractPhone(from);

            // Find user by phone
            const user = await this.findUserByPhone(phone);
            if (!user) {
                // Unknown user — send welcome message
                await this.sendUnknownUserMessage(phone);
                return;
            }

            // Clean and normalize the message
            const command = (body || '').trim().toLowerCase();

            // Route to appropriate handler
            let response = null;

            if (this.commands.ripoti.test(command)) {
                response = await this.handleReportRequest(user);
            } else if (this.commands.mauzo.test(command)) {
                response = await this.handleSalesRequest(user);
            } else if (this.commands.faida.test(command)) {
                response = await this.handleProfitRequest(user);
            } else if (this.commands.wiki.test(command)) {
                response = await this.handleWeeklyReportRequest(user);
            } else if (this.commands.msaada.test(command)) {
                response = this.handleHelpRequest(user);
            } else if (this.commands.shiriki.test(command)) {
                response = this.handleShareRequest(user);
            } else if (this.commands.simama.test(command)) {
                response = await this.handleStopRequest(user);
            } else if (this.commands.anza.test(command)) {
                response = await this.handleStartRequest(user);
            } else if (this.commands.kiswahili.test(command)) {
                response = await this.handleLanguageChange(user, 'sw');
            } else if (this.commands.sheng.test(command)) {
                response = await this.handleLanguageChange(user, 'sheng');
            } else if (this.commands.english.test(command)) {
                response = await this.handleLanguageChange(user, 'en');
            } else if (this.commands.hali.test(command)) {
                response = await this.handleStatusRequest(user);
            } else {
                // Unknown command — send help
                response = this.handleUnknownCommand(user);
            }

            // Send response
            if (response) {
                await this.client.sendText(phone, response);
                console.log(`[MessageHandler] Response sent to ${phone}`);
            }

        } catch (error) {
            console.error('[MessageHandler] Error handling message:', error);

            // Send error message to user
            try {
                const phone = this.extractPhone(message.from);
                await this.client.sendText(phone,
                    '😔 Kuna tatzo. Tafadhali jaribu tena baadaye.\n\n' +
                    'Tuma "msaada" kwa msaada.'
                );
            } catch (sendError) {
                console.error('[MessageHandler] Error sending error message:', sendError);
            }
        }
    }

    /**
     * Handle "ripoti" / "report" command.
     * Returns today's full report.
     */
    async handleReportRequest(user) {
        const report = await this.reportGenerator.generate({
            userId: user.userId,
            reportType: 'daily',
            date: new Date().toISOString().split('T')[0],
            assistantName: user.assistantName,
            userName: user.userName,
            language: user.language
        });

        return report;
    }

    /**
     * Handle "mauzo" / "sales" command.
     * Returns sales summary only.
     */
    async handleSalesRequest(user) {
        const data = await this.reportGenerator.fetchBusinessData(
            user.userId, 'daily', new Date().toISOString().split('T')[0]
        );

        const messages = {
            sw: `💰 *Mauzo ya Leo*\n\n` +
                `Jumla: KSh ${this.reportGenerator.formatNumber(data.sales)}\n` +
                `Bidhaa: ${data.itemsSold}\n` +
                `Bidhaa bora: ${data.topProduct} (KSh ${this.reportGenerator.formatNumber(data.topProductSales)})\n\n` +
                `Tuma "ripoti" kwa ripoti kamili.`,
            sheng: `💰 *Sales ya Leo*\n\n` +
                `Total: KSh ${this.reportGenerator.formatNumber(data.sales)}\n` +
                `Items: ${data.itemsSold}\n` +
                `Best seller: ${data.topProduct} (KSh ${this.reportGenerator.formatNumber(data.topProductSales)})\n\n` +
                `Tuma "ripoti" kwa full report.`,
            en: `💰 *Today's Sales*\n\n` +
                `Total: KSh ${this.reportGenerator.formatNumber(data.sales)}\n` +
                `Items: ${data.itemsSold}\n` +
                `Top product: ${data.topProduct} (KSh ${this.reportGenerator.formatNumber(data.topProductSales)})\n\n` +
                `Send "report" for full report.`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle "faida" / "profit" command.
     * Returns profit summary only.
     */
    async handleProfitRequest(user) {
        const data = await this.reportGenerator.fetchBusinessData(
            user.userId, 'daily', new Date().toISOString().split('T')[0]
        );

        const messages = {
            sw: `📈 *Faida ya Leo*\n\n` +
                `Faida: KSh ${this.reportGenerator.formatNumber(data.profit)}\n` +
                `Mauzo: KSh ${this.reportGenerator.formatNumber(data.sales)}\n` +
                `Margin: ${((data.profit / data.sales) * 100).toFixed(1)}%\n\n` +
                `Tuma "ripoti" kwa ripoti kamili.`,
            sheng: `📈 *Profit ya Leo*\n\n` +
                `Profit: KSh ${this.reportGenerator.formatNumber(data.profit)}\n` +
                `Sales: KSh ${this.reportGenerator.formatNumber(data.sales)}\n` +
                `Margin: ${((data.profit / data.sales) * 100).toFixed(1)}%\n\n` +
                `Tuma "ripoti" kwa full report.`,
            en: `📈 *Today's Profit*\n\n` +
                `Profit: KSh ${this.reportGenerator.formatNumber(data.profit)}\n` +
                `Sales: KSh ${this.reportGenerator.formatNumber(data.sales)}\n` +
                `Margin: ${((data.profit / data.sales) * 100).toFixed(1)}%\n\n` +
                `Send "report" for full report.`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle "wiki" / "weekly" command.
     * Returns weekly report.
     */
    async handleWeeklyReportRequest(user) {
        const report = await this.reportGenerator.generate({
            userId: user.userId,
            reportType: 'weekly',
            date: new Date().toISOString().split('T')[0],
            assistantName: user.assistantName,
            userName: user.userName,
            language: user.language
        });

        return report;
    }

    /**
     * Handle "msaada" / "help" command.
     * Shows available commands.
     */
    handleHelpRequest(user) {
        const messages = {
            sw: `📋 *Orodha ya Amri — ${user.assistantName}*\n\n` +
                `📊 *ripoti* — Ripoti ya leo\n` +
                `💰 *mauzo* — Muhtasari wa mauzo\n` +
                `📈 *faida* — Muhtasari wa faida\n` +
                `📅 *wiki* — Ripoti ya wiki\n` +
                `📤 *shiriki* — Shiriki na rafiki\n` +
                `📋 *msaada* — Orodha hii\n` +
                `🛑 *simama* — Acha ripoti\n` +
                `▶️ *anza* — Anza ripoti tena\n\n` +
                `*Lugha:*\n` +
                `🇹🇿 *kiswahili* — Kiswahili\n` +
                `🇰🇪 *sheng* — Sheng\n` +
                `🇬🇧 *english* — English\n\n` +
                `_Tuma amri yoyote kupata taarifa._`,
            sheng: `📋 *Menu ya Amri — ${user.assistantName}*\n\n` +
                `📊 *ripoti* — Report ya leo\n` +
                `💰 *mauzo* — Sales summary\n` +
                `📈 *faida* — Profit summary\n` +
                `📅 *wiki* — Weekly report\n` +
                `📤 *shiriki* — Share na boys\n` +
                `📋 *msaada* — Menu hii\n` +
                `🛑 *simama* — Stop reports\n` +
                `▶️ *anza* — Start tena\n\n` +
                `*Lugha:*\n` +
                `🇹🇿 *kiswahili* — Kiswahili\n` +
                `🇰🇪 *sheng* — Sheng\n` +
                `🇬🇧 *english* — English\n\n` +
                `_Tuma command yoyote._`,
            en: `📋 *Command List — ${user.assistantName}*\n\n` +
                `📊 *report* — Today's report\n` +
                `💰 *sales* — Sales summary\n` +
                `📈 *profit* — Profit summary\n` +
                `📅 *weekly* — Weekly report\n` +
                `📤 *share* — Share with friends\n` +
                `📋 *help* — This list\n` +
                `🛑 *stop* — Stop reports\n` +
                `▶️ *start* — Resume reports\n\n` +
                `*Language:*\n` +
                `🇹🇿 *swahili* — Kiswahili\n` +
                `🇰🇪 *sheng* — Sheng\n` +
                `🇬🇧 *english* — English\n\n` +
                `_Send any command to get info._`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle "shiriki" / "share" command.
     * Returns share message with download link.
     */
    handleShareRequest(user) {
        const messages = {
            sw: `🎉 *${user.assistantName} — Msaidizi wa Biashara!*\n\n` +
                `Ninatumia ${user.assistantName} kurekodi mauzo yangu kwa sauti. Inafanya kazi bila internet!\n\n` +
                `📱 Pakua bure: https://github.com/msaidizi/releases\n` +
                `💬 Jiunge na WhatsApp: https://chat.whatsapp.com/msaidizi-group`,
            sheng: `🎉 *${user.assistantName} — Msaidizi wa Biashara!*\n\n` +
                `Natumia ${user.assistantName} kurekodi sales zangu kwa sauti. Inafanya kazi bila net! 💪\n\n` +
                `📱 Download bure: https://github.com/msaidizi/releases\n` +
                `💬 Join group: https://chat.whatsapp.com/msaidizi-group`,
            en: `🎉 *${user.assistantName} — Business Assistant!*\n\n` +
                `I use ${user.assistantName} to record my sales by voice. It works offline!\n\n` +
                `📱 Download free: https://github.com/msaidizi/releases\n` +
                `💬 Join WhatsApp: https://chat.whatsapp.com/msaidizi-group`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle "simama" / "stop" command.
     * Unsubscribes user from daily reports.
     */
    async handleStopRequest(user) {
        await WhatsAppService.updateReportPreference(user.userId, false);

        const messages = {
            sw: `🛑 *Ripoti zimesitishwa.*\n\nSita kutumia ripoti tena.\n\nTuma "anza" kurudi tena.`,
            sheng: `🛑 *Reports zimesimama.*\n\nSita kutumia reports tena.\n\nTuma "anza" kurudi.`,
            en: `🛑 *Reports stopped.*\n\nI won't send you reports anymore.\n\nSend "start" to resume.`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle "anza" / "start" command.
     * Resubscribes user to daily reports.
     */
    async handleStartRequest(user) {
        await WhatsAppService.updateReportPreference(user.userId, true);

        const messages = {
            sw: `▶️ *Ripoti zimeanza tena!*\n\nSasa utapata ripoti za biashara kila siku.\n\nTuma "msaada" kuona amri zote.`,
            sheng: `▶️ *Reports zimerudi!*\n\nSasa utapata reports za biashara daily.\n\nTuma "msaada" kuona commands zote.`,
            en: `▶️ *Reports resumed!*\n\nYou'll receive daily business reports again.\n\nSend "help" to see all commands.`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle language change command.
     */
    async handleLanguageChange(user, language) {
        await WhatsAppService.updateLanguage(user.userId, language);

        const messages = {
            sw: `🇹🇿 *Lugha imebadilishwa kuwa Kiswahili!*\n\nSasa nitazungumza nawe kwa Kiswahili.`,
            sheng: `🇰🇪 *Lugha imebadilishwa kuwa Sheng!*\n\nSasa nitazungumza nawe kwa Sheng. Poa! 💪`,
            en: `🇬🇧 *Language changed to English!*\n\nI'll now communicate in English.`
        };

        return messages[language] || messages.sw;
    }

    /**
     * Handle status request.
     */
    async handleStatusRequest(user) {
        const connection = await WhatsAppService.getConnection(user.userId);

        const messages = {
            sw: `📱 *Hali ya Muungano*\n\n` +
                `👤 Mtumiaji: ${user.userName}\n` +
                `🤖 Msaidizi: ${user.assistantName}\n` +
                `📱 Namba: ${user.phone}\n` +
                `✅ Imeunganishwa: ${connection.connectedAt}\n` +
                `📊 Ripoti: ${connection.reportTime}\n` +
                `🌍 Lugha: ${this.getLanguageName(user.language)}\n` +
                `📩 Ripoti ya mwisho: ${connection.lastReportSent || 'Bado'}`,
            sheng: `📱 *Status ya Connection*\n\n` +
                `👤 User: ${user.userName}\n` +
                `🤖 Msaidizi: ${user.assistantName}\n` +
                `📱 Namba: ${user.phone}\n` +
                `✅ Connected: ${connection.connectedAt}\n` +
                `📊 Reports: ${connection.reportTime}\n` +
                `🌍 Lugha: ${this.getLanguageName(user.language)}\n` +
                `📩 Last report: ${connection.lastReportSent || 'Bado'}`,
            en: `📱 *Connection Status*\n\n` +
                `👤 User: ${user.userName}\n` +
                `🤖 Assistant: ${user.assistantName}\n` +
                `📱 Phone: ${user.phone}\n` +
                `✅ Connected: ${connection.connectedAt}\n` +
                `📊 Reports: ${connection.reportTime}\n` +
                `🌍 Language: ${this.getLanguageName(user.language)}\n` +
                `📩 Last report: ${connection.lastReportSent || 'Not yet'}`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Handle unknown command.
     */
    handleUnknownCommand(user) {
        const messages = {
            sw: `🤔 Sijaelewa.\n\nTuma "msaada" kuona amri zote.`,
            sheng: `🤔 Sijaelewa boss.\n\nTuma "msaada" kuona commands zote.`,
            en: `🤔 I didn't understand.\n\nSend "help" to see all commands.`
        };

        return messages[user.language] || messages.sw;
    }

    /**
     * Send message to unknown user.
     */
    async sendUnknownUserMessage(phone) {
        const message = `👋 Habari!\n\n` +
            `Mimi ni Msaidizi wa Biashara — ninakusaidia kurekodi mauzo yako kwa sauti.\n\n` +
            `📱 Pakua Msaidizi: https://github.com/msaidizi/releases\n` +
            `💬 Jiunge na WhatsApp: https://chat.whatsapp.com/msaidizi-group\n\n` +
            `Baada ya kujisajili, utapata ripoti za biashara hapa kila siku!`;

        await this.client.sendText(phone, message);
    }

    /**
     * Extract phone number from OpenWA format.
     * 254712345678@c.us → +254712345678
     */
    extractPhone(from) {
        const cleaned = from.replace('@c.us', '').replace('@g.us', '');
        return `+${cleaned}`;
    }

    /**
     * Find user by phone number.
     */
    async findUserByPhone(phone) {
        // This would query the database in production
        // For now, check in-memory connections
        const connections = await WhatsAppService.getAllConnectedUsers();
        return connections.find(c => c.phone === phone) || null;
    }

    /**
     * Get language display name.
     */
    getLanguageName(language) {
        const names = {
            sw: 'Kiswahili',
            sheng: 'Sheng',
            en: 'English'
        };
        return names[language] || language;
    }
}

module.exports = MessageHandler;
