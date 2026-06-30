/**
 * ReportGenerator — Generates business reports for WhatsApp delivery.
 * 
 * Supports:
 *  - Daily reports (sales, profit, tips)
 *  - Weekly reports (summary, trends)
 *  - Custom date ranges
 * 
 * Reports are formatted in the user's preferred language (Swahili, Sheng, English).
 */

class ReportGenerator {

    /**
     * Generate a report for a user.
     * 
     * @param {Object} params
     * @param {string} params.userId - User ID
     * @param {string} params.reportType - "daily" or "weekly"
     * @param {string} params.date - ISO date string (YYYY-MM-DD)
     * @param {string} params.assistantName - What user named Msaidizi
     * @param {string} params.userName - User's name
     * @param {string} params.language - "sw", "sheng", or "en"
     * @returns {Promise<string>} Formatted report text
     */
    async generate({ userId, reportType, date, assistantName, userName, language }) {
        // Fetch business data from database
        const data = await this.fetchBusinessData(userId, reportType, date);

        if (reportType === 'weekly') {
            return this.generateWeeklyReport({ data, assistantName, userName, language });
        }

        return this.generateDailyReport({ data, assistantName, userName, language, date });
    }

    /**
     * Fetch business data from database.
     * This would query the actual database in production.
     */
    async fetchBusinessData(userId, reportType, date) {
        // TODO: Replace with actual database query
        // For now, return mock data
        return {
            sales: Math.floor(Math.random() * 10000) + 500,
            itemsSold: Math.floor(Math.random() * 50) + 5,
            profit: Math.floor(Math.random() * 3000) + 100,
            topProduct: 'Mandazi',
            topProductSales: Math.floor(Math.random() * 2000) + 500,
            lowStockItems: ['Maziwa', 'Sukari'],
            tip: this.getRandomTip(language),
            weeklySales: [
                { day: 'Jumatatu', amount: Math.floor(Math.random() * 5000) + 1000 },
                { day: 'Jumanne', amount: Math.floor(Math.random() * 5000) + 1000 },
                { day: 'Jumatano', amount: Math.floor(Math.random() * 5000) + 1000 },
                { day: 'Alhamisi', amount: Math.floor(Math.random() * 5000) + 1000 },
                { day: 'Ijumaa', amount: Math.floor(Math.random() * 5000) + 1000 },
                { day: 'Jumamosi', amount: Math.floor(Math.random() * 5000) + 1000 },
                { day: 'Jumapili', amount: Math.floor(Math.random() * 5000) + 1000 }
            ]
        };
    }

    /**
     * Generate daily report.
     */
    generateDailyReport({ data, assistantName, userName, language, date }) {
        const templates = {
            sw: this.buildDailySwahili(data, assistantName, userName),
            sheng: this.buildDailySheng(data, assistantName, userName),
            en: this.buildDailyEnglish(data, assistantName, userName)
        };

        return templates[language] || templates.sw;
    }

    /**
     * Build daily report in Swahili.
     */
    buildDailySwahili(data, assistantName, userName) {
        let report = `📊 *Ripoti ya Leo — ${assistantName}*\n\n`;
        report += `👤 ${userName}, hii leo:\n`;
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
     * Build daily report in Sheng.
     */
    buildDailySheng(data, assistantName, userName) {
        let report = `📊 *Report ya Leo — ${assistantName}*\n\n`;
        report += `👤 ${userName}, leo:\n`;
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
     * Build daily report in English.
     */
    buildDailyEnglish(data, assistantName, userName) {
        let report = `📊 *Today's Report — ${assistantName}*\n\n`;
        report += `👤 ${userName}, today:\n`;
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
     * Generate weekly report.
     */
    generateWeeklyReport({ data, assistantName, userName, language }) {
        const templates = {
            sw: this.buildWeeklySwahili(data, assistantName, userName),
            sheng: this.buildWeeklySheng(data, assistantName, userName),
            en: this.buildWeeklyEnglish(data, assistantName, userName)
        };

        return templates[language] || templates.sw;
    }

    /**
     * Build weekly report in Swahili.
     */
    buildWeeklySwahili(data, assistantName, userName) {
        let report = `📊 *Ripoti ya Wiki — ${assistantName}*\n\n`;
        report += `👤 ${userName}, wiki hii:\n`;
        report += `💰 Mauzo jumla: KSh ${this.formatNumber(data.sales)}\n`;
        report += `📈 Faida jumla: KSh ${this.formatNumber(data.profit)}\n\n`;

        if (data.weeklySales && data.weeklySales.length > 0) {
            const sorted = [...data.weeklySales].sort((a, b) => b.amount - a.amount);
            const best = sorted[0];
            const worst = sorted[sorted.length - 1];

            report += `📊 Mauzo ya juu: ${best.day} (KSh ${this.formatNumber(best.amount)})\n`;
            report += `📉 Mauzo ya chini: ${worst.day} (KSh ${this.formatNumber(worst.amount)})\n\n`;

            // Daily breakdown
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
     * Build weekly report in Sheng.
     */
    buildWeeklySheng(data, assistantName, userName) {
        let report = `📊 *Report ya Wiki — ${assistantName}*\n\n`;
        report += `👤 ${userName}, wiki hii:\n`;
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
     * Build weekly report in English.
     */
    buildWeeklyEnglish(data, assistantName, userName) {
        let report = `📊 *Weekly Report — ${assistantName}*\n\n`;
        report += `👤 ${userName}, this week:\n`;
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
     * Generate share message.
     */
    generateShareMessage({ assistantName, language }) {
        const messages = {
            sw: `🎉 ${assistantName} — Msaidizi wa Biashara!\n\nNinatumia ${assistantName} kurekodi mauzo yangu kwa sauti. Inafanya kazi bila internet!\n\nPakua bure: https://github.com/msaidizi/releases\nJiunge na WhatsApp: https://chat.whatsapp.com/msaidizi-group`,
            sheng: `🎉 ${assistantName} — Msaidizi wa Biashara!\n\nNatumia ${assistantName} kurekodi sales zangu kwa sauti. Inafanya kazi bila net! 💪\n\nDownload bure: https://github.com/msaidizi/releases\nJoin WhatsApp group: https://chat.whatsapp.com/msaidizi-group`,
            en: `🎉 ${assistantName} — Business Assistant!\n\nI use ${assistantName} to record my sales by voice. It works offline!\n\nDownload free: https://github.com/msaidizi/releases\nJoin WhatsApp: https://chat.whatsapp.com/msaidizi-group`
        };

        return messages[language] || messages.sw;
    }

    /**
     * Get a random business tip.
     */
    getRandomTip(language) {
        const tips = {
            sw: [
                'Mandazi yanaongezeka soko leo. Ongeza stock!',
                'Jumatatu ndio soko yako bora. Fungua mapema!',
                'Wateja wanaanza kuja saa 10. Hakikisha uko tayari!',
                'Ongeza bei ya bidhaa zinazouzwa sana — mahitaji yapo!',
                'Fanya hesabu za mwisho wa siku kabla ya kufunga.',
                'Wateja wanaopenda huduma nzuri hurudi tena. Tabasamu!',
                'Sukari inauzwa sana wiki hii. Ongeza order!',
                'Punguza bei ya bidhaa zinazokaa sana — cash flow ni muhimu!'
            ],
            sheng: [
                'Mandazi zinapiga soko leo. Increase stock! 💪',
                'Monday ndio best day yako. Open mapema!',
                'Customers wanaanza kuja saa 10. Kuwa ready!',
                'Ongeza bei ya items zinazouzwa — demand iko!',
                'Fanya hesabu za evening kabla ya kufunga.',
                'Customers wanaopenda poa service hurudi. Smile!',
                'Sukari inauzwa sana wiki hii. Order more!',
                'Punguza bei ya slow movers — cash flow ni king!'
            ],
            en: [
                'Mandazi are selling well today. Stock up!',
                'Monday is your best sales day. Open early!',
                'Customers start coming at 10 AM. Be ready!',
                'Raise prices on fast-selling items — demand is there!',
                'Do your end-of-day calculations before closing.',
                'Customers who get good service come back. Smile!',
                'Sugar is selling fast this week. Order more!',
                'Discount slow-moving items — cash flow is king!'
            ]
        };

        const langTips = tips[language] || tips.sw;
        return langTips[Math.floor(Math.random() * langTips.length)];
    }

    /**
     * Format number with commas (Kenyan format).
     * 1234567 → 1,234,567
     */
    formatNumber(num) {
        if (num === null || num === undefined) return '0';
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

module.exports = ReportGenerator;
