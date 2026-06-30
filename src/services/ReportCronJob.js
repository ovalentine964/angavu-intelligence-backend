const cron = require('node-cron');
const WhatsAppService = require('../services/WhatsAppService');
const ReportGenerator = require('../services/ReportGenerator');
const OpenWAClient = require('../openwa/OpenWAClient');

class ReportCronJob {
    constructor() {
        this.client = OpenWAClient.getInstance();
        this.reportGenerator = new ReportGenerator();
        this.jobs = [];
    }

    start() {
        console.log('[ReportCron] Starting report cron jobs...');
        this.jobs.push(cron.schedule('0 5 * * *', () => this.sendReportsForTime('morning'), { timezone: 'Africa/Nairobi' }));
        this.jobs.push(cron.schedule('0 10 * * *', () => this.sendReportsForTime('afternoon'), { timezone: 'Africa/Nairobi' }));
        this.jobs.push(cron.schedule('0 15 * * *', () => this.sendReportsForTime('evening'), { timezone: 'Africa/Nairobi' }));
        this.jobs.push(cron.schedule('0 15 * * 0', () => this.sendWeeklyReports(), { timezone: 'Africa/Nairobi' }));
        console.log('[ReportCron] All cron jobs started.');
    }

    stop() {
        console.log('[ReportCron] Stopping report cron jobs...');
        this.jobs.forEach(job => job.stop());
        this.jobs = [];
    }

    async sendReportsForTime(reportTime) {
        console.log(`[ReportCron] Sending ${reportTime} reports...`);
        try {
            const users = await WhatsAppService.getUsersForReportTime(reportTime);
            console.log(`[ReportCron] Found ${users.length} users for ${reportTime} reports`);
            let successCount = 0, failCount = 0;
            for (const user of users) {
                try {
                    const isConnected = await this.client.isConnected();
                    if (!isConnected) { console.error('[ReportCron] OpenWA not connected'); break; }
                    const report = await this.reportGenerator.generate({ userId: user.userId, reportType: 'daily', date: new Date().toISOString().split('T')[0], assistantName: user.assistantName, userName: user.userName, language: user.language });
                    const result = await this.client.sendText(user.phone, report);
                    if (result && result.id) { await WhatsAppService.updateLastReportSent(user.userId); successCount++; } else failCount++;
                    await this.sleep(1000);
                } catch (error) { failCount++; console.error(`[ReportCron] Error sending to ${user.phone}:`, error.message); }
            }
            console.log(`[ReportCron] ${reportTime} reports: ${successCount} sent, ${failCount} failed`);
        } catch (error) { console.error(`[ReportCron] Error in ${reportTime} reports:`, error); }
    }

    async sendWeeklyReports() {
        console.log('[ReportCron] Sending weekly reports...');
        try {
            const allUsers = await WhatsAppService.getAllConnectedUsers();
            let successCount = 0, failCount = 0;
            for (const user of allUsers) {
                try {
                    const isConnected = await this.client.isConnected();
                    if (!isConnected) break;
                    const report = await this.reportGenerator.generate({ userId: user.userId, reportType: 'weekly', date: new Date().toISOString().split('T')[0], assistantName: user.assistantName, userName: user.userName, language: user.language });
                    const result = await this.client.sendText(user.phone, report);
                    if (result && result.id) { await WhatsAppService.updateLastReportSent(user.userId); successCount++; } else failCount++;
                    await this.sleep(1000);
                } catch (error) { failCount++; }
            }
            console.log(`[ReportCron] Weekly reports: ${successCount} sent, ${failCount} failed`);
        } catch (error) { console.error('[ReportCron] Error in weekly reports:', error); }
    }

    sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
}

module.exports = ReportCronJob;
