use serde::{Deserialize, Serialize};
use anyhow::{Result, Context};

/// WhatsApp Business API message types.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MessageType {
    Text,
    Template,
    Interactive,
}

/// A WhatsApp message to send.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WhatsAppMessage {
    pub to: String,
    pub content: String,
    pub message_type: MessageType,
    pub template_name: Option<String>,
    pub template_params: Option<Vec<String>>,
}

/// Delivery status from WhatsApp Business API.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeliveryStatus {
    pub status: String,
    pub timestamp: String,
    pub message_id: Option<String>,
    pub error: Option<String>,
}

/// WhatsApp Business API response.
#[derive(Debug, Clone, Deserialize)]
struct WhatsAppApiResponse {
    messaging_product: String,
    contacts: Option<Vec<WhatsAppContact>>,
    messages: Option<Vec<WhatsAppMessageId>>,
}

#[derive(Debug, Clone, Deserialize)]
struct WhatsAppContact {
    input: String,
    wa_id: String,
}

#[derive(Debug, Clone, Deserialize)]
struct WhatsAppMessageId {
    id: String,
}

/// Error response from WhatsApp API.
#[derive(Debug, Clone, Deserialize)]
struct WhatsAppError {
    error: WhatsAppErrorDetail,
}

#[derive(Debug, Clone, Deserialize)]
struct WhatsAppErrorDetail {
    message: String,
    #[serde(rename = "type")]
    error_type: String,
    code: u32,
}

pub struct WhatsAppSender {
    api_url: String,
    api_key: String,
    phone_number_id: String,
    from_number: String,
}

impl WhatsAppSender {
    /// Create a new sender using environment variables:
    /// - WHATSAPP_API_KEY: Bearer token for the WhatsApp Business API
    /// - WHATSAPP_PHONE_NUMBER_ID: The sending phone number ID
    /// - WHATSAPP_API_URL: (optional) API base URL, defaults to Meta Graph API
    /// - WHATSAPP_FROM_NUMBER: (optional) Sender phone number
    pub fn new() -> Self {
        let api_key = std::env::var("WHATSAPP_API_KEY")
            .unwrap_or_default();
        let phone_number_id = std::env::var("WHATSAPP_PHONE_NUMBER_ID")
            .unwrap_or_default();
        let api_url = std::env::var("WHATSAPP_API_URL")
            .unwrap_or_else(|_| "https://graph.facebook.com/v18.0".to_string());
        let from_number = std::env::var("WHATSAPP_FROM_NUMBER")
            .unwrap_or_default();

        Self { api_url, api_key, phone_number_id, from_number }
    }

    /// Create with explicit configuration (useful for testing).
    pub fn with_config(api_url: &str, api_key: &str, phone_number_id: &str, from_number: &str) -> Self {
        Self {
            api_url: api_url.to_string(),
            api_key: api_key.to_string(),
            phone_number_id: phone_number_id.to_string(),
            from_number: from_number.to_string(),
        }
    }

    /// Validate that the sender is properly configured.
    pub fn is_configured(&self) -> bool {
        !self.api_key.is_empty() && !self.phone_number_id.is_empty()
    }

    /// Build the API endpoint URL for sending messages.
    fn endpoint(&self) -> String {
        format!("{}/{}/messages", self.api_url, self.phone_number_id)
    }

    /// Send a text message via WhatsApp Business API.
    pub async fn send_text(&self, to: &str, message: &str) -> Result<DeliveryStatus> {
        if !self.is_configured() {
            return Ok(DeliveryStatus {
                status: "error".to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                message_id: None,
                error: Some("WhatsApp API not configured. Set WHATSAPP_API_KEY and WHATSAPP_PHONE_NUMBER_ID".to_string()),
            });
        }

        let body = serde_json::json!({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {
                "body": message
            }
        });

        self.send_request(&body).await
    }

    /// Send a template message (for notifications, reports, etc.).
    pub async fn send_template(
        &self,
        to: &str,
        template_name: &str,
        params: &[String],
    ) -> Result<DeliveryStatus> {
        if !self.is_configured() {
            return Ok(DeliveryStatus {
                status: "error".to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                message_id: None,
                error: Some("WhatsApp API not configured".to_string()),
            });
        }

        let components = if params.is_empty() {
            serde_json::json!([])
        } else {
            serde_json::json!([{
                "type": "body",
                "parameters": params.iter().map(|p| {
                    serde_json::json!({"type": "text", "text": p})
                }).collect::<Vec<_>>()
            }])
        };

        let body = serde_json::json!({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": { "code": "en" },
                "components": components
            }
        });

        self.send_request(&body).await
    }

    /// Send a business report as a formatted WhatsApp message.
    pub async fn send_report(&self, phone: &str, report_content: &str) -> Result<DeliveryStatus> {
        let formatted = self.format_for_whatsapp(report_content);
        self.send_text(phone, &formatted).await
    }

    /// Format content for WhatsApp's simplified markdown.
    /// WhatsApp supports: *bold*, _italic_, ~strikethrough~, ```monospace```
    pub fn format_for_whatsapp(&self, content: &str) -> String {
        content
            .replace("**", "*")   // Markdown bold → WhatsApp bold
            .replace("__", "_")   // Markdown italic → WhatsApp italic
            .replace("```", "`")  // Code blocks → inline code
    }

    /// Internal: send HTTP request to WhatsApp Business API.
    async fn send_request(&self, body: &serde_json::Value) -> Result<DeliveryStatus> {
        let client = reqwest::Client::new();
        let url = self.endpoint();

        let response = client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .body(body.to_string())
            .send()
            .await
            .context("Failed to send WhatsApp API request")?;

        let status_code = response.status().as_u16();
        let response_text = response.text().await
            .context("Failed to read WhatsApp API response")?;

        if (200..300).contains(&status_code) {
            let api_resp: WhatsAppApiResponse = serde_json::from_str(&response_text)
                .unwrap_or(WhatsAppApiResponse {
                    messaging_product: "whatsapp".to_string(),
                    contacts: None,
                    messages: None,
                });
            let message_id = api_resp.messages
                .and_then(|msgs| msgs.first().map(|m| m.id.clone()));

            Ok(DeliveryStatus {
                status: "sent".to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                message_id,
                error: None,
            })
        } else {
            let error_detail = serde_json::from_str::<WhatsAppError>(&response_text)
                .map(|e| format!("{}: {}", e.error.error_type, e.error.message))
                .unwrap_or_else(|_| response_text.clone());

            Ok(DeliveryStatus {
                status: "failed".to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                message_id: None,
                error: Some(error_detail),
            })
        }
    }

    /// Validate a phone number format (basic E.164 check).
    pub fn validate_phone(phone: &str) -> bool {
        let cleaned: String = phone.chars().filter(|c| c.is_ascii_digit() || *c == '+').collect();
        // E.164: +{country}{number}, 8-15 digits total
        if cleaned.starts_with('+') {
            let digits: String = cleaned.chars().skip(1).collect();
            digits.len() >= 7 && digits.len() <= 14 && digits.chars().all(|c| c.is_ascii_digit())
        } else {
            cleaned.len() >= 7 && cleaned.len() <= 15 && cleaned.chars().all(|c| c.is_ascii_digit())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_for_whatsapp() {
        let sender = WhatsAppSender::with_config("", "", "", "");
        let input = "Revenue **up** by __15%__ and ```code```";
        let output = sender.format_for_whatsapp(input);
        assert_eq!(output, "Revenue *up* by _15%_ and `code`");
    }

    #[test]
    fn test_validate_phone_valid() {
        assert!(WhatsAppSender::validate_phone("+254712345678"));
        assert!(WhatsAppSender::validate_phone("+14155551234"));
        assert!(WhatsAppSender::validate_phone("254712345678"));
    }

    #[test]
    fn test_validate_phone_invalid() {
        assert!(!WhatsAppSender::validate_phone(""));
        assert!(!WhatsAppSender::validate_phone("123"));
        assert!(!WhatsAppSender::validate_phone("abcdefghij"));
        assert!(!WhatsAppSender::validate_phone("+"));
    }

    #[test]
    fn test_is_configured() {
        let configured = WhatsAppSender::with_config(
            "https://graph.facebook.com/v18.0",
            "test-token",
            "123456",
            "+254700000000",
        );
        assert!(configured.is_configured());

        let unconfigured = WhatsAppSender::with_config("", "", "", "");
        assert!(!unconfigured.is_configured());
    }

    #[test]
    fn test_endpoint_url() {
        let sender = WhatsAppSender::with_config(
            "https://graph.facebook.com/v18.0",
            "token",
            "phone123",
            "",
        );
        assert_eq!(sender.endpoint(), "https://graph.facebook.com/v18.0/phone123/messages");
    }

    #[tokio::test]
    async fn test_send_text_unconfigured() {
        let sender = WhatsAppSender::with_config("", "", "", "");
        let result = sender.send_text("+254712345678", "test").await.unwrap();
        assert_eq!(result.status, "error");
        assert!(result.error.is_some());
    }

    #[tokio::test]
    async fn test_send_template_unconfigured() {
        let sender = WhatsAppSender::with_config("", "", "", "");
        let result = sender.send_template("+254712345678", "daily_report", &["param1".to_string()]).await.unwrap();
        assert_eq!(result.status, "error");
    }

    #[tokio::test]
    async fn test_send_report_unconfigured() {
        let sender = WhatsAppSender::with_config("", "", "", "");
        let result = sender.send_report("+254712345678", "📊 Daily Report\n**Revenue**: $1000").await.unwrap();
        assert_eq!(result.status, "error");
    }

    #[test]
    fn test_delivery_status_serialization() {
        let status = DeliveryStatus {
            status: "sent".to_string(),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
            message_id: Some("msg_123".to_string()),
            error: None,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("msg_123"));
        assert!(json.contains("sent"));
    }
}
