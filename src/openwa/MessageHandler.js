const WhatsAppService = require('../services/WhatsAppService');
const ReportGenerator = require('../services/ReportGenerator');
const OpenWAClient = require('./OpenWAClient');

class MessageHandler {
    constructor() {
        this.client = OpenWAClient.getInstance();
        this.reportGenerator = new ReportGenerator();
        this.commands = {
            ripoti: /^(ripoti|report|leo|today)$/i,
            mauzo: /^(mauzo|sales|sold)$/i,
            faida: /^(faida|profit|mapato)$/i,
            wiki: /^(wiki|weekly|week)$/i,
            msaada: /^(msaada|help|sos|menu)$/i,
            shiriki: /^(shiriki|share|tuma|send)$/i,
            simama: /^(simama|stop|cancel|ondoa)$/i,
            anza: /^(anza|start|subscribe|jiunge)$/i,
            kiswahili: /^(sw|swahili|kiswahili)$/i,
            sheng: /^(sheng|sh)$/i,
            english: /^(en|english|kingereza)$/i,
            hali: /^(hali|status|state)$/i
        };
    }

    async handleMessage(message) {
        try {
            const { from, body } = message;
            const phone = this.extractPhone(from);
            const user = await this.findUserByPhone(phone);
            if (!user) { await this.sendUnknownUserMessage(phone); return; }

            const command = (body || '').trim().toLowerCase();
            let response = null;

            if (this.commands.ripoti.test(command)) response = await this.handleReportRequest(user);
            else if (this.commands.mauzo.test(command)) response = await this.handleSalesRequest(user);
            else if (this.commands.faida.test(command)) response = await this.handleProfitRequest(user);
            else if (this.commands.wiki.test(command)) response = await this.handleWeeklyReportRequest(user);
            else if (this.commands.msaada.test(command)) response = this.handleHelpRequest(user);
            else if (this.commands.shiriki.test(command)) response = this.handleShareRequest(user);
            else if (this.commands.simama.test(command)) response = await this.handleStopRequest(user);
            else if (this.commands.anza.test(command)) response = await this.handleStartRequest(user);
            else if (this.commands.kiswahili.test(command)) response = await this.handleLanguageChange(user, 'sw');
            else if (this.commands.sheng.test(command)) response = await this.handleLanguageChange(user, 'sheng');
            else if (this.commands.english.test(command)) response = await this.handleLanguageChange(user, 'en');
            else if (this.commands.hali.test(command)) response = await this.handleStatusRequest(user);
            else response = this.handleUnknownCommand(user);

            if (response) await this.client.sendText(phone, response);
        } catch (error) {
            console.error('[MessageHandler] Error:', error);
            try { await this.client.sendText(this.extractPhone(message.from), '😔 Kuna tatzo. Tafadhali jaribu tena.\n\nTuma "msaada" kwa msaada.'); } catch (e) {}
        }
    }

    async handleReportRequest(user) {
        return await this.reportGenerator.generate({ userId: user.userId, reportType: 'daily', date: new Date().toISOString().split('T')[0], assistantName: user.assistantName, userName: user.userName, language: user.language });
    }

    async handleSalesRequest(user) {
        const data = await this.reportGenerator.fetchBusinessData(user.userId, 'daily', new Date().toISOString().split('T')[0]);
        const messages = {
            sw: `💰 *Mauzo ya Leo*\n\nJumla: KSh ${this.reportGenerator.formatNumber(data.sales)}\nBidhaa: ${data.itemsSold}\nBidhaa bora: ${data.topProduct} (KSh ${this.reportGenerator.formatNumber(data.topProductSales)})\n\nTuma "ripoti" kwa ripoti kamili.`,
            sheng: `💰 *Sales ya Leo*\n\nTotal: KSh ${this.reportGenerator.formatNumber(data.sales)}\nItems: ${data.itemsSold}\nBest seller: ${data.topProduct} (KSh ${this.reportGenerator.formatNumber(data.topProductSales)})\n\nTuma "ripoti" kwa full report.`,
            en: `💰 *Today's Sales*\n\nTotal: KSh ${this.reportGenerator.formatNumber(data.sales)}\nItems: ${data.itemsSold}\nTop product: ${data.topProduct} (KSh ${this.reportGenerator.formatNumber(data.topProductSales)})\n\nSend "report" for full report.`
        };
        return messages[user.language] || messages.sw;
    }

    async handleProfitRequest(user) {
        const data = await this.reportGenerator.fetchBusinessData(user.userId, 'daily', new Date().toISOString().split('T')[0]);
        const margin = ((data.profit / data.sales) * 100).toFixed(1);
        const messages = {
            sw: `📈 *Faida ya Leo*\n\nFaida: KSh ${this.reportGenerator.formatNumber(data.profit)}\nMauzo: KSh ${this.reportGenerator.formatNumber(data.sales)}\nMargin: ${margin}%\n\nTuma "ripoti" kwa ripoti kamili.`,
            sheng: `📈 *Profit ya Leo*\n\nProfit: KSh ${this.reportGenerator.formatNumber(data.profit)}\nSales: KSh ${this.reportGenerator.formatNumber(data.sales)}\nMargin: ${margin}%\n\nTuma "ripoti" kwa full report.`,
            en: `📈 *Today's Profit*\n\nProfit: KSh ${this.reportGenerator.formatNumber(data.profit)}\nSales: KSh ${this.reportGenerator.formatNumber(data.sales)}\nMargin: ${margin}%\n\nSend "report" for full report.`
        };
        return messages[user.language] || messages.sw;
    }

    async handleWeeklyReportRequest(user) {
        return await this.reportGenerator.generate({ userId: user.userId, reportType: 'weekly', date: new Date().toISOString().split('T')[0], assistantName: user.assistantName, userName: user.userName, language: user.language });
    }

    handleHelpRequest(user) {
        const messages = {
            sw: `📋 *Orodha ya Amri — ${user.assistantName}*\n\n📊 *ripoti* — Ripoti ya leo\n💰 *mauzo* — Muhtasari wa mauzo\n📈 *faida* — Muhtasari wa faida\n📅 *wiki* — Ripoti ya wiki\n📤 *shiriki* — Shiriki na rafiki\n📋 *msaada* — Orodha hii\n🛑 *simama* — Acha ripoti\n▶️ *anza* — Anza ripoti tena\n\n*Lugha:*\n🇹🇿 *kiswahili* — Kiswahili\n🇰🇪 *sheng* — Sheng\n🇬🇧 *english* — English\n\n_Tuma amri yoyote kupata taarifa._`,
            sheng: `📋 *Menu ya Amri — ${user.assistantName}*\n\n📊 *ripoti* — Report ya leo\n💰 *mauzo* — Sales summary\n📈 *faida* — Profit summary\n📅 *wiki* — Weekly report\n📤 *shiriki* — Share na boys\n📋 *msaada* — Menu hii\n🛑 *simama* — Stop reports\n▶️ *anza* — Start tena\n\n*Lugha:*\n🇹🇿 *kiswahili* — Kiswahili\n🇰🇪 *sheng* — Sheng\n🇬🇧 *english* — English\n\n_Tuma command yoyote._`,
            en: `📋 *Command List — ${user.assistantName}*\n\n📊 *report* — Today's report\n💰 *sales* — Sales summary\n📈 *profit* — Profit summary\n📅 *weekly* — Weekly report\n📤 *share* — Share with friends\n📋 *help* — This list\n🛑 *stop* — Stop reports\n▶️ *start* — Resume reports\n\n*Language:*\n🇹🇿 *swahili* — Kiswahili\n🇰🇪 *sheng* — Sheng\n🇬🇧 *english* — English\n\n_Send any command to get info._`
        };
        return messages[user.language] || messages.sw;
    }

    handleShareRequest(user) {
        return this.reportGenerator.generateShareMessage({ assistantName: user.assistantName, language: user.language });
    }

    async handleStopRequest(user) {
        await WhatsAppService.updateReportPreference(user.userId, false);
        const messages = { sw: `🛑 *Ripoti zimesitishwa.*\n\nSita kutumia ripoti tena.\n\nTuma "anza" kurudi tena.`, sheng: `🛑 *Reports zimesimama.*\n\nSita kutumia reports tena.\n\nTuma "anza" kurudi.`, en: `🛑 *Reports stopped.*\n\nI won't send you reports anymore.\n\nSend "start" to resume.` };
        return messages[user.language] || messages.sw;
    }

    async handleStartRequest(user) {
        await WhatsAppService.updateReportPreference(user.userId, true);
        const messages = { sw: `▶️ *Ripoti zimeanza tena!*\n\nSasa utapata ripoti za biashara kila siku.\n\nTuma "msaada" kuona amri zote.`, sheng: `▶️ *Reports zimerudi!*\n\nSasa utapata reports za biashara daily.\n\nTuma "msaada" kuona commands zote.`, en: `▶️ *Reports resumed!*\n\nYou'll receive daily business reports again.\n\nSend "help" to see all commands.` };
        return messages[user.language] || messages.sw;
    }

    async handleLanguageChange(user, language) {
        await WhatsAppService.updateLanguage(user.userId, language);
        const messages = { sw: `🇹🇿 *Lugha imebadilishwa kuwa Kiswahili!*\n\nSasa nitazungumza nawe kwa Kiswahili.`, sheng: `🇰🇪 *Lugha imebadilishwa kuwa Sheng!*\n\nSasa nitazungumza nawe kwa Sheng. Poa! 💪`, en: `🇬🇧 *Language changed to English!*\n\nI'll now communicate in English.` };
        return messages[language] || messages.sw;
    }

    async handleStatusRequest(user) {
        const connection = await WhatsAppService.getConnection(user.userId);
        const langName = { sw: 'Kiswahili', sheng: 'Sheng', en: 'English' };
        const messages = {
            sw: `📱 *Hali ya Muungano*\n\n👤 Mtumiaji: ${user.userName}\n🤖 Msaidizi: ${user.assistantName}\n📱 Namba: ${user.phone}\n✅ Imeunganishwa: ${connection?.connectedAt}\n📊 Ripoti: ${connection?.reportTime}\n🌍 Lugha: ${langName[user.language]}\n📩 Ripoti ya mwisho: ${connection?.lastReportSent || 'Bado'}`,
            sheng: `📱 *Status ya Connection*\n\n👤 User: ${user.userName}\n🤖 Msaidizi: ${user.assistantName}\n📱 Namba: ${user.phone}\n✅ Connected: ${connection?.connectedAt}\n📊 Reports: ${connection?.reportTime}\n🌍 Lugha: ${langName[user.language]}\n📩 Last report: ${connection?.lastReportSent || 'Bado'}`,
            en: `📱 *Connection Status*\n\n👤 User: ${user.userName}\n🤖 Assistant: ${user.assistantName}\n📱 Phone: ${user.phone}\n✅ Connected: ${connection?.connectedAt}\n📊 Reports: ${connection?.reportTime}\n🌍 Language: ${langName[user.language]}\n📩 Last report: ${connection?.lastReportSent || 'Not yet'}`
        };
        return messages[user.language] || messages.sw;
    }

    handleUnknownCommand(user) {
        const messages = { sw: `🤔 Sijaelewa.\n\nTuma "msaada" kuona amri zote.`, sheng: `🤔 Sijaelewa boss.\n\nTuma "msaada" kuona commands zote.`, en: `🤔 I didn't understand.\n\nSend "help" to see all commands.` };
        return messages[user.language] || messages.sw;
    }

    async sendUnknownUserMessage(phone) {
        await this.client.sendText(phone, `👋 Habari!\n\nMimi ni Msaidizi wa Biashara — ninakusaidia kurekodi mauzo yako kwa sauti.\n\n📱 Pakua Msaidizi: https://github.com/msaidizi/releases\n💬 Jiunge na WhatsApp: https://chat.whatsapp.com/msaidizi-group\n\nBaada ya kujisajili, utapata ripoti za biashara hapa kila siku!`);
    }

    extractPhone(from) { return `+${from.replace('@c.us', '').replace('@g.us', '')}`; }
    async findUserByPhone(phone) { const connections = await WhatsAppService.getAllConnectedUsers(); return connections.find(c => c.phone === phone) || null; }
}

module.exports = MessageHandler;
