use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize)]
pub struct WhatsAppMessage {
    pub to: String,
    pub content: String,
    pub message_type: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DeliveryStatus {
    pub status: String,
    pub timestamp: String,
}

pub struct WhatsAppSender;

impl WhatsAppSender {
    pub fn new() -> Self { Self }

    pub fn send_report(&self, phone: &str, report_content: &str) -> Result<DeliveryStatus> {
        // In production: integrate with WhatsApp Business API via OpenWA
        Ok(DeliveryStatus {
            status: "sent".to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
        })
    }

    pub fn format_for_whatsapp(&self, content: &str) -> String {
        // WhatsApp uses simplified markdown
        content.replace("**", "*").replace("__", "_")
    }
}
