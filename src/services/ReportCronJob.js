/**
 * Report Cron Job
 * 
 * Sends daily and weekly reports to connected users at their preferred time.
 * 
 * Schedule:
 *  - Morning reports: 8:00 AM EAT
 *  - Afternoon reports: 1:00 PM EAT
 *  - Evening reports: 6:00 PM EAT
 *  - Weekly reports: Sunday 6:00 PM EAT
 */

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

    /**
     * Start all cron jobs.
     */
    start() {
        console.log('[ReportCron] Starting report cron jobs...');

        // Morning reports — 8:00 AM EAT (5:00 AM UTC)
        this.jobs.push(cron.schedule('0 5 * * *', () => {
            this.sendReportsForTime('morning');
        }, {
            timezone: 'Africa/Nairobi'
        }));

        // Afternoon reports — 1:00 PM EAT (10:00 AM UTC)
        this.jobs.push(cron.schedule('0 10 * * *', () => {
            this.sendReportsForTime('afternoon');
        }, {
            timezone: 'Africa/Nairobi'
        }));

        // Evening reports — 6:00 PM EAT (3:00 PM UTC)
        this.jobs.push(cron.schedule('0 15 * * *', () => {
            this.sendReportsForTime('evening');
        }, {
            timezone: 'Africa/Nairobi'
        }));

        // Weekly reports — Sunday 6:00 PM EAT
        this.jobs.push(cron.schedule('0 15 * * 0', () => {
            this.sendWeeklyReports();
        }, {
            timezone: 'Africa/Nairobi'
        }));

        console.log('[ReportCron] All cron jobs started.');
    }

    /**
     * Stop all cron jobs.
     */
    stop() {
        console.log('[ReportCron] Stopping report cron jobs...');
        this.jobs.forEach(job => job.stop());
        this.jobs = [];
        console.log('[ReportCron] All cron jobs stopped.');
    }

    /**
     * Send reports for a specific time slot.
     */
    async sendReportsForTime(reportTime) {
        console.log(`[ReportCron] Sending ${reportTime} reports...`);

        try {
            const users = await WhatsAppService.getUsersForReportTime(reportTime);
            console.log(`[ReportCron] Found ${users.length} users for ${reportTime} reports`);

            let successCount = 0;
            let failCount = 0;

            for (const user of users) {
                try {
                    // Check if OpenWA is connected
                    const isConnected = await this.client.isConnected();
                    if (!isConnected) {
                        console.error('[ReportCron] OpenWA not connected, skipping...');
                        break;
                    }

                    // Generate report
                    const report = await this.reportGenerator.generate({
                        userId: user.userId,
                        reportType: 'daily',
                        date: new Date().toISOString().split('T')[0],
                        assistantName: user.assistantName,
                        userName: user.userName,
                        language: user.language
                    });

                    // Send via WhatsApp
                    const result = await this.client.sendText(user.phone, report);

                    if (result && result.id) {
                        // Update last report sent
                        await WhatsAppService.updateLastReportSent(user.userId);
                        successCount++;
                        console.log(`[ReportCron] Report sent to ${user.phone}`);
                    } else {
                        failCount++;
                        console.error(`[ReportCron] Failed to send report to ${user.phone}`);
                    }

                    // Rate limiting: wait 1 second between messages
                    await this.sleep(1000);

                } catch (error) {
                    failCount++;
                    console.error(`[ReportCron] Error sending report to ${user.phone}:`, error.message);
                }
            }

            console.log(`[ReportCron] ${reportTime} reports complete: ${successCount} sent, ${failCount} failed`);

        } catch (error) {
            console.error(`[ReportCron] Error in ${reportTime} reports:`, error);
        }
    }

    /**
     * Send weekly reports.
     */
    async sendWeeklyReports() {
        console.log('[ReportCron] Sending weekly reports...');

        try {
            const allUsers = await WhatsAppService.getAllConnectedUsers();
            console.log(`[ReportCron] Found ${allUsers.length} users for weekly reports`);

            let successCount = 0;
            let failCount = 0;

            for (const user of allUsers) {
                try {
                    // Check if OpenWA is connected
                    const isConnected = await this.client.isConnected();
                    if (!isConnected) {
                        console.error('[ReportCron] OpenWA not connected, skipping...');
                        break;
                    }

                    // Generate weekly report
                    const report = await this.reportGenerator.generate({
                        userId: user.userId,
                        reportType: 'weekly',
                        date: new Date().toISOString().split('T')[0],
                        assistantName: user.assistantName,
                        userName: user.userName,
                        language: user.language
                    });

                    // Send via WhatsApp
                    const result = await this.client.sendText(user.phone, report);

                    if (result && result.id) {
                        await WhatsAppService.updateLastReportSent(user.userId);
                        successCount++;
                        console.log(`[ReportCron] Weekly report sent to ${user.phone}`);
                    } else {
                        failCount++;
                    }

                    // Rate limiting
                    await this.sleep(1000);

                } catch (error) {
                    failCount++;
                    console.error(`[ReportCron] Error sending weekly report to ${user.phone}:`, error.message);
                }
            }

            console.log(`[ReportCron] Weekly reports complete: ${successCount} sent, ${failCount} failed`);

        } catch (error) {
            console.error('[ReportCron] Error in weekly reports:', error);
        }
    }

    /**
     * Sleep utility.
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

module.exports = ReportCronJob;
