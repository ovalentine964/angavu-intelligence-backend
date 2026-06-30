/**
 * WhatsApp Report Templates
 * 
 * Predefined templates for different report types and languages.
 * These templates are used by ReportGenerator to create consistent reports.
 */

class ReportTemplates {

    /**
     * Get daily report template
     */
    static getDailyTemplate(language, data) {
        const templates = {
            sw: this.dailySwahili(data),
            sheng: this.dailySheng(data),
            en: this.dailyEnglish(data)
        };

        return templates[language] || templates.sw;
    }

    /**
     * Get weekly report template
     */
    static getWeeklyTemplate(language, data) {
        const templates = {
            sw: this.weeklySwahili(data),
            sheng: this.weeklySheng(data),
            en: this.weeklyEnglish(data)
        };

        return templates[language] || templates.sw;
    }

    /**
     * Get share message template
     */
    static getShareTemplate(language, assistantName) {
        const templates = {
            sw: `🎉 *${assistantName} — Msaidizi wa Biashara!*\n\n` +
                `Ninatumia ${assistantName} kurekodi mauzo yangu kwa sauti. Inafanya kazi bila internet!\n\n` +
                `📱 Pakua bure: https://github.com/msaidizi/releases\n` +
                `💬 Jiunge na WhatsApp: https://chat.whatsapp.com/msaidizi-group`,
            sheng: `🎉 *${assistantName} — Msaidizi wa Biashara!*\n\n` +
                `Natumia ${assistantName} kurekodi sales zangu kwa sauti. Inafanya kazi bila net! 💪\n\n` +
                `📱 Download bure: https://github.com/msaidizi/releases\n` +
                `💬 Join group: https://chat.whatsapp.com/msaidizi-group`,
            en: `🎉 *${assistantName} — Business Assistant!*\n\n` +
                `I use ${assistantName} to record my sales by voice. It works offline!\n\n` +
                `📱 Download free: https://github.com/msaidizi/releases\n` +
                `💬 Join WhatsApp: https://chat.whatsapp.com/msaidizi-group`
        };

        return templates[language] || templates.sw;
    }

    /**
     * Get welcome message template
     */
    static getWelcomeTemplate(language, userName, assistantName) {
        const templates = {
            sw: `🎉 Habari ${userName}!\n\n` +
                `${assistantName} wako ameunganishwa na Msaidizi wa Biashara!\n\n` +
                `Sasa utapata:\n` +
                `📊 Ripoti za biashara kila siku\n` +
                `💰 Muhtasari wa mauzo na faida\n` +
                `💡 Vidokezo vya kuboresha biashara\n\n` +
                `Karibu! 🚀\n\n` +
                `_Tuma "ripoti" kupata ripoti ya leo_\n` +
                `_Tuma "mauzo" kupata muhtasari wa mauzo_\n` +
                `_Tuma "faida" kupata muhtasari wa faida_`,
            sheng: `🎉 Sana ${userName}!\n\n` +
                `${assistantName} wako ame-connect na Msaidizi wa Biashara! 💪\n\n` +
                `Sasa utapata:\n` +
                `📊 Report ya biashara daily\n` +
                `💰 Sales na profit summary\n` +
                `💡 Tips za kuboresha biashara\n\n` +
                `Karibu boss! 🔥\n\n` +
                `_Tuma "ripoti" kwa report ya leo_\n` +
                `_Tuma "mauzo" kwa sales summary_\n` +
                `_Tuma "faida" kwa profit summary_`,
            en: `🎉 Hello ${userName}!\n\n` +
                `${assistantName} is now connected to Msaidizi Business Assistant!\n\n` +
                `You'll receive:\n` +
                `📊 Daily business reports\n` +
                `💰 Sales and profit summaries\n` +
                `💡 Tips to grow your business\n\n` +
                `Welcome aboard! 🚀\n\n` +
                `_Send "report" for today's report_\n` +
                `_Send "sales" for sales summary_\n` +
                `_Send "profit" for profit summary_`
        };

        return templates[language] || templates.sw;
    }

    /**
     * Get help message template
     */
    static getHelpTemplate(language, assistantName) {
        const templates = {
            sw: `📋 *Orodha ya Amri — ${assistantName}*\n\n` +
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
            sheng: `📋 *Menu ya Amri — ${assistantName}*\n\n` +
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
            en: `📋 *Command List — ${assistantName}*\n\n` +
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

        return templates[language] || templates.sw;
    }

    // ── Private template builders ──────────────────────────────────────────

    /**
     * Daily report in Swahili
     */
    static dailySwahili(data) {
        let report = `📊 *Ripoti ya Leo — ${data.assistantName}*\n\n`;
        report += `👤 ${data.userName}, hii leo:\n`;
        report += `💰 Mauzo: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📦 Bidhaa zilizouzwa: ${data.itemsSold}\n`;
        report += `📈 Faida: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.topProduct) {
            report += `🏆 Bidhaa bora: ${data.topProduct} (KSh ${this.formatNumber(data.topProductSales)})\n`;
        }

        if (data.lowStockItems && data.lowStockItems.length > 0) {
            report += `⚠️ Stock inayokaribia kuisha: ${data.lowStockItems.join(', ')}\n`;
        }

        report += `\n💡 *Kidokezo: ${data.tip}*\n\n`;
        report += `🔗 Pakua Msaidizi: https://github.com/msaidizi/releases\n`;
        report += `📤 Shiriki na rafiki: https://msaidizi.app/share`;

        return report;
    }

    /**
     * Daily report in Sheng
     */
    static dailySheng(data) {
        let report = `📊 *Report ya Leo — ${data.assistantName}*\n\n`;
        report += `👤 ${data.userName}, leo:\n`;
        report += `💰 Sales: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📦 Items zilizouzwa: ${data.itemsSold}\n`;
        report += `📈 Profit: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.topProduct) {
            report += `🏆 Best seller: ${data.topProduct} (KSh ${this.formatNumber(data.topProductSales)})\n`;
        }

        if (data.lowStockItems && data.lowStockItems.length > 0) {
            report += `⚠️ Stock ya kuisha: ${data.lowStockItems.join(', ')}\n`;
        }

        report += `\n💡 *Tip: ${data.tip}*\n\n`;
        report += `🔗 Download Msaidizi: https://github.com/msaidizi/releases\n`;
        report += `📤 Share na boys: https://msaidizi.app/share`;

        return report;
    }

    /**
     * Daily report in English
     */
    static dailyEnglish(data) {
        let report = `📊 *Today's Report — ${data.assistantName}*\n\n`;
        report += `👤 ${data.userName}, today:\n`;
        report += `💰 Sales: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📦 Items sold: ${data.itemsSold}\n`;
        report += `📈 Profit: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.topProduct) {
            report += `🏆 Top product: ${data.topProduct} (KSh ${this.formatNumber(data.topProductSales)})\n`;
        }

        if (data.lowStockItems && data.lowStockItems.length > 0) {
            report += `⚠️ Low stock: ${data.lowStockItems.join(', ')}\n`;
        }

        report += `\n💡 *Tip: ${data.tip}*\n\n`;
        report += `🔗 Download Msaidizi: https://github.com/msaidizi/releases\n`;
        report += `📤 Share with friends: https://msaidizi.app/share`;

        return report;
    }

    /**
     * Weekly report in Swahili
     */
    static weeklySwahili(data) {
        let report = `📊 *Ripoti ya Wiki — ${data.assistantName}*\n\n`;
        report += `👤 ${data.userName}, wiki hii:\n`;
        report += `💰 Mauzo jumla: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📈 Faida jumla: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.weeklySales && data.weeklySales.length > 0) {
            const sorted = [...data.weeklySales].sort((a, b) => b.amount - a.amount);
            const best = sorted[0];
            const worst = sorted[sorted.length - 1];

            report += `📊 Mauzo ya juu: ${best.day} (KSh ${this.formatNumber(best.amount)})\n`;
            report += `📉 Mauzo ya chini: ${worst.day} (KSh ${this.formatNumber(worst.amount)})\n\n`;

            report += `📅 Mauzo ya kila siku:\n`;
            for (const day of data.weeklySales) {
                const bar = '█'.repeat(Math.floor(day.amount / 1000));
                report += `  ${day.day}: ${bar} KSh ${this.formatNumber(day.amount)}\n`;
            }
        }

        report += `\n💡 *Kidokezo: ${data.tip}*\n\n`;
        report += `🔗 Pakua Msaidizi: https://github.com/msaidizi/releases`;

        return report;
    }

    /**
     * Weekly report in Sheng
     */
    static weeklySheng(data) {
        let report = `📊 *Report ya Wiki — ${data.assistantName}*\n\n`;
        report += `👤 ${data.userName}, wiki hii:\n`;
        report += `💰 Total sales: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📈 Total profit: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.weeklySales && data.weeklySales.length > 0) {
            const sorted = [...data.weeklySales].sort((a, b) => b.amount - a.amount);
            const best = sorted[0];
            const worst = sorted[sorted.length - 1];

            report += `📊 Best day: ${best.day} (KSh ${this.formatNumber(best.amount)})\n`;
            report += `📉 Worst day: ${worst.day} (KSh ${this.formatNumber(worst.amount)})\n\n`;

            report += `📅 Daily breakdown:\n`;
            for (const day of data.weeklySales) {
                const bar = '█'.repeat(Math.floor(day.amount / 1000));
                report += `  ${day.day}: ${bar} KSh ${this.formatNumber(day.amount)}\n`;
            }
        }

        report += `\n💡 *Tip: ${data.tip}*\n\n`;
        report += `🔗 Download Msaidizi: https://github.com/msaidizi/releases`;

        return report;
    }

    /**
     * Weekly report in English
     */
    static weeklyEnglish(data) {
        let report = `📊 *Weekly Report — ${data.assistantName}*\n\n`;
        report += `👤 ${data.userName}, this week:\n`;
        report += `💰 Total sales: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📈 Total profit: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.weeklySales && data.weeklySales.length > 0) {
            const sorted = [...data.weeklySales].sort((a, b) => b.amount - a.amount);
            const best = sorted[0];
            const worst = sorted[sorted.length - 1];

            report += `📊 Best day: ${best.day} (KSh ${this.formatNumber(best.amount)})\n`;
            report += `📉 Worst day: ${worst.day} (KSh ${this.formatNumber(worst.amount)})\n\n`;

            report += `📅 Daily breakdown:\n`;
            for (const day of data.weeklySales) {
                const bar = '█'.repeat(Math.floor(day.amount / 1000));
                report += `  ${day.day}: ${bar} KSh ${this.formatNumber(day.amount)}\n`;
            }
        }

        report += `\n💡 *Tip: ${data.tip}*\n\n`;
        report += `🔗 Download Msaidizi: https://github.com/msaidizi/releases`;

        return report;
    }

    /**
     * Format number with commas
     */
    static formatNumber(num) {
        if (num === null || num === undefined) return '0';
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

module.exports = ReportTemplates;
