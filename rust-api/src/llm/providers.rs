// =============================================================================
// Angavu Intelligence — Model-Agnostic LLM Provider Abstraction
// "Harness is permanent, model is swappable"
//
// Design: ModelProvider trait enables runtime model switching without changing
// the orchestration harness. New providers (GPT-4, future AGI models) implement
// the trait and register with the engine.
// =============================================================================

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

use super::{CircuitBreaker, LlmConfig, LlmResponse};

// ── Model Provider Trait ─────────────────────────────────────────────────────

/// Trait for all LLM providers. Implement this to add a new model backend.
///
/// Design principles:
/// - Provider is stateless per-request (state lives in CircuitBreaker/registry)
/// - Provider declares its capabilities so the engine can route intelligently
/// - Provider handles its own HTTP/auth; engine handles retry/fallback/circuit-breaking
/// - Future AGI providers implement this same trait — harness doesn't change
#[async_trait]
pub trait ModelProvider: Send + Sync {
    /// Unique provider identifier (e.g., "deepseek-reasoner", "qwen-7b", "gpt-4o")
    fn id(&self) -> &str;

    /// Human-readable provider name
    fn name(&self) -> &str;

    /// Model capabilities — used for intelligent routing
    fn capabilities(&self) -> ModelCapabilities;

    /// Execute a single inference request
    async fn infer(&self, request: &InferenceRequest) -> Result<InferenceResponse, ProviderError>;

    /// Health check — returns true if provider is reachable
    async fn health_check(&self) -> bool;

    /// Whether this provider is currently available (key exists, circuit not open)
    fn is_configured(&self) -> bool;
}

// ── Model Capabilities ───────────────────────────────────────────────────────

/// Describes what a model can do — used for intelligent routing
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelCapabilities {
    /// Maximum context window (tokens)
    pub max_context_tokens: u32,
    /// Maximum output tokens
    pub max_output_tokens: u32,
    /// Whether the model supports reasoning/chain-of-thought
    pub supports_reasoning: bool,
    /// Whether the model supports structured output (JSON mode)
    pub supports_structured_output: bool,
    /// Whether the model supports tool/function calling
    pub supports_tool_use: bool,
    /// Whether the model supports multimodal input (images, audio)
    pub supports_multimodal: bool,
    /// Approximate cost per 1M input tokens (USD)
    pub cost_per_million_input: f64,
    /// Approximate cost per 1M output tokens (USD)
    pub cost_per_million_output: f64,
    /// Latency tier: "fast" (<1s), "medium" (1-5s), "slow" (5-30s), "deep" (30s+)
    pub latency_tier: String,
    /// Quality tier: "basic", "good", "excellent", "agi"
    pub quality_tier: String,
    /// Specializations (e.g., ["credit_analysis", "multilingual", "reasoning"])
    pub specializations: Vec<String>,
}

impl Default for ModelCapabilities {
    fn default() -> Self {
        Self {
            max_context_tokens: 4096,
            max_output_tokens: 2048,
            supports_reasoning: false,
            supports_structured_output: false,
            supports_tool_use: false,
            supports_multimodal: false,
            cost_per_million_input: 0.0,
            cost_per_million_output: 0.0,
            latency_tier: "medium".to_string(),
            quality_tier: "good".to_string(),
            specializations: vec![],
        }
    }
}

// ── Inference Request/Response ───────────────────────────────────────────────

/// Provider-agnostic inference request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceRequest {
    pub prompt: String,
    pub system_prompt: Option<String>,
    pub max_tokens: Option<u32>,
    pub temperature: Option<f32>,
    pub response_format: Option<ResponseFormat>,
    /// Task type for routing decisions
    pub task_type: TaskType,
    /// Priority level
    pub priority: RequestPriority,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ResponseFormat {
    Text,
    Json,
    StructuredJson(String), // JSON schema
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TaskType {
    CreditAnalysis,
    MarketAnalysis,
    Conversation,
    Summarization,
    Translation,
    Reasoning,
    CodeGeneration,
    General,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RequestPriority {
    Low,
    Normal,
    High,
    Critical,
}

/// Provider-agnostic inference response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceResponse {
    pub content: String,
    pub model_used: String,
    pub provider_id: String,
    pub tokens_input: u32,
    pub tokens_output: u32,
    pub latency_ms: u64,
    pub finish_reason: FinishReason,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FinishReason {
    Stop,
    Length,
    ToolCall,
    ContentFilter,
    Error,
}

/// Provider error types
#[derive(Debug, thiserror::Error)]
pub enum ProviderError {
    #[error("Authentication failed: {0}")]
    AuthFailed(String),
    #[error("Rate limited: {0}")]
    RateLimited(String),
    #[error("Context window exceeded: {0} tokens requested")]
    ContextExceeded(u32),
    #[error("Model unavailable: {0}")]
    Unavailable(String),
    #[error("Request timeout after {0}ms")]
    Timeout(u64),
    #[error("Provider error: {0}")]
    Internal(String),
}

// ── Model Registry ───────────────────────────────────────────────────────────

/// Registry of all available model providers with intelligent routing
pub struct ModelRegistry {
    providers: RwLock<HashMap<String, Arc<dyn ModelProvider>>>,
    /// Routing rules: task_type → preferred provider order
    routing_rules: RwLock<HashMap<TaskType, Vec<String>>>,
    /// Default provider when no routing rule matches
    default_provider: RwLock<Option<String>>,
}

impl ModelRegistry {
    pub fn new() -> Self {
        Self {
            providers: RwLock::new(HashMap::new()),
            routing_rules: RwLock::new(HashMap::new()),
            default_provider: RwLock::new(None),
        }
    }

    /// Register a model provider
    pub async fn register(&self, provider: Arc<dyn ModelProvider>) {
        let id = provider.id().to_string();
        info!("Registering model provider: {} ({})", provider.name(), id);
        self.providers.write().await.insert(id, provider);
    }

    /// Set routing rule: which provider to prefer for a task type
    pub async fn set_routing(&self, task_type: TaskType, provider_order: Vec<String>) {
        self.routing_rules.write().await.insert(task_type, provider_order);
    }

    /// Set default provider
    pub async fn set_default(&self, provider_id: String) {
        *self.default_provider.write().await = Some(provider_id);
    }

    /// Get the best provider for a given task
    pub async fn resolve(&self, task_type: TaskType) -> Option<Arc<dyn ModelProvider>> {
        let providers = self.providers.read().await;
        let routing = self.routing_rules.read().await;

        // Try routing rules first
        if let Some(order) = routing.get(&task_type) {
            for provider_id in order {
                if let Some(provider) = providers.get(provider_id) {
                    if provider.is_configured() {
                        return Some(provider.clone());
                    }
                }
            }
        }

        // Fall back to default
        let default = self.default_provider.read().await;
        if let Some(ref default_id) = *default {
            if let Some(provider) = providers.get(default_id) {
                if provider.is_configured() {
                    return Some(provider.clone());
                }
            }
        }

        // Fall back to any configured provider
        for provider in providers.values() {
            if provider.is_configured() {
                return Some(provider.clone());
            }
        }

        None
    }

    /// List all registered providers and their status
    pub async fn list_providers(&self) -> Vec<ProviderInfo> {
        let providers = self.providers.read().await;
        providers
            .values()
            .map(|p| ProviderInfo {
                id: p.id().to_string(),
                name: p.name().to_string(),
                configured: p.is_configured(),
                capabilities: p.capabilities(),
            })
            .collect()
    }
}

#[derive(Debug, Serialize)]
pub struct ProviderInfo {
    pub id: String,
    pub name: String,
    pub configured: bool,
    pub capabilities: ModelCapabilities,
}

// ── Concrete Provider: DeepSeek ──────────────────────────────────────────────

pub struct DeepSeekProvider {
    model_name: String,
    api_key: Option<String>,
    base_url: String,
    http: reqwest::Client,
    capabilities: ModelCapabilities,
}

impl DeepSeekProvider {
    pub fn new(model_name: &str, api_key: Option<String>, base_url: String, http: reqwest::Client) -> Self {
        let capabilities = match model_name {
            "deepseek-reasoner" => ModelCapabilities {
                max_context_tokens: 65536,
                max_output_tokens: 16384,
                supports_reasoning: true,
                supports_structured_output: true,
                supports_tool_use: false,
                supports_multimodal: false,
                cost_per_million_input: 0.55,
                cost_per_million_output: 2.19,
                latency_tier: "slow".to_string(),
                quality_tier: "excellent".to_string(),
                specializations: vec!["reasoning".to_string(), "credit_analysis".to_string()],
            },
            "deepseek-chat" => ModelCapabilities {
                max_context_tokens: 65536,
                max_output_tokens: 8192,
                supports_reasoning: false,
                supports_structured_output: true,
                supports_tool_use: true,
                supports_multimodal: false,
                cost_per_million_input: 0.27,
                cost_per_million_output: 1.10,
                latency_tier: "fast".to_string(),
                quality_tier: "good".to_string(),
                specializations: vec!["conversation".to_string(), "general".to_string()],
            },
            _ => ModelCapabilities::default(),
        };

        Self {
            model_name: model_name.to_string(),
            api_key,
            base_url,
            http,
            capabilities,
        }
    }
}

#[async_trait]
impl ModelProvider for DeepSeekProvider {
    fn id(&self) -> &str {
        &self.model_name
    }

    fn name(&self) -> &str {
        match self.model_name.as_str() {
            "deepseek-reasoner" => "DeepSeek Reasoner",
            "deepseek-chat" => "DeepSeek Chat",
            _ => "DeepSeek (unknown)",
        }
    }

    fn capabilities(&self) -> ModelCapabilities {
        self.capabilities.clone()
    }

    async fn infer(&self, request: &InferenceRequest) -> Result<InferenceResponse, ProviderError> {
        let api_key = self
            .api_key
            .as_ref()
            .ok_or_else(|| ProviderError::AuthFailed("No DeepSeek API key configured".to_string()))?;

        let url = format!("{}/chat/completions", self.base_url);

        let body = serde_json::json!({
            "model": self.model_name,
            "messages": [
                if let Some(ref sys) = request.system_prompt {
                    serde_json::json!({"role": "system", "content": sys})
                } else {
                    serde_json::json!({"role": "system", "content": "You are a helpful assistant."})
                },
                {"role": "user", "content": request.prompt}
            ],
            "max_tokens": request.max_tokens.unwrap_or(2048),
            "temperature": request.temperature.unwrap_or(0.7),
        });

        let start = std::time::Instant::now();
        let response = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
            .map_err(|e| ProviderError::Internal(format!("HTTP error: {}", e)))?;

        let status = response.status();
        if status == 401 || status == 403 {
            return Err(ProviderError::AuthFailed(format!("HTTP {}", status)));
        }
        if status == 429 {
            return Err(ProviderError::RateLimited("Rate limited by DeepSeek".to_string()));
        }
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(ProviderError::Internal(format!("HTTP {}: {}", status, body)));
        }

        let latency_ms = start.elapsed().as_millis() as u64;
        let resp: serde_json::Value = response
            .json()
            .await
            .map_err(|e| ProviderError::Internal(format!("Parse error: {}", e)))?;

        let content = resp["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("")
            .to_string();

        Ok(InferenceResponse {
            content,
            model_used: self.model_name.clone(),
            provider_id: self.model_name.clone(),
            tokens_input: resp["usage"]["prompt_tokens"].as_u64().unwrap_or(0) as u32,
            tokens_output: resp["usage"]["completion_tokens"].as_u64().unwrap_or(0) as u32,
            latency_ms,
            finish_reason: FinishReason::Stop,
        })
    }

    async fn health_check(&self) -> bool {
        self.api_key.is_some()
    }

    fn is_configured(&self) -> bool {
        self.api_key.is_some() && !self.api_key.as_ref().unwrap().is_empty()
    }
}

// ── Concrete Provider: Qwen ──────────────────────────────────────────────────

pub struct QwenProvider {
    model_name: String,
    api_key: Option<String>,
    base_url: String,
    http: reqwest::Client,
}

impl QwenProvider {
    pub fn new(model_name: &str, api_key: Option<String>, base_url: String, http: reqwest::Client) -> Self {
        Self {
            model_name: model_name.to_string(),
            api_key,
            base_url,
            http,
        }
    }
}

#[async_trait]
impl ModelProvider for QwenProvider {
    fn id(&self) -> &str {
        &self.model_name
    }

    fn name(&self) -> &str {
        "Qwen"
    }

    fn capabilities(&self) -> ModelCapabilities {
        ModelCapabilities {
            max_context_tokens: 32768,
            max_output_tokens: 8192,
            supports_reasoning: false,
            supports_structured_output: true,
            supports_tool_use: true,
            supports_multimodal: false,
            cost_per_million_input: 0.30,
            cost_per_million_output: 0.60,
            latency_tier: "fast".to_string(),
            quality_tier: "good".to_string(),
            specializations: vec!["multilingual".to_string(), "conversation".to_string()],
        }
    }

    async fn infer(&self, request: &InferenceRequest) -> Result<InferenceResponse, ProviderError> {
        let api_key = self
            .api_key
            .as_ref()
            .ok_or_else(|| ProviderError::AuthFailed("No Qwen API key configured".to_string()))?;

        let url = format!("{}/chat/completions", self.base_url);

        let body = serde_json::json!({
            "model": self.model_name,
            "messages": [
                if let Some(ref sys) = request.system_prompt {
                    serde_json::json!({"role": "system", "content": sys})
                } else {
                    serde_json::json!({"role": "system", "content": "You are a helpful assistant."})
                },
                {"role": "user", "content": request.prompt}
            ],
            "max_tokens": request.max_tokens.unwrap_or(2048),
            "temperature": request.temperature.unwrap_or(0.7),
        });

        let start = std::time::Instant::now();
        let response = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
            .map_err(|e| ProviderError::Internal(format!("HTTP error: {}", e)))?;

        let status = response.status();
        if status == 401 || status == 403 {
            return Err(ProviderError::AuthFailed(format!("HTTP {}", status)));
        }
        if status == 429 {
            return Err(ProviderError::RateLimited("Rate limited by Qwen".to_string()));
        }
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(ProviderError::Internal(format!("HTTP {}: {}", status, body)));
        }

        let latency_ms = start.elapsed().as_millis() as u64;
        let resp: serde_json::Value = response
            .json()
            .await
            .map_err(|e| ProviderError::Internal(format!("Parse error: {}", e)))?;

        let content = resp["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("")
            .to_string();

        Ok(InferenceResponse {
            content,
            model_used: self.model_name.clone(),
            provider_id: self.model_name.clone(),
            tokens_input: resp["usage"]["prompt_tokens"].as_u64().unwrap_or(0) as u32,
            tokens_output: resp["usage"]["completion_tokens"].as_u64().unwrap_or(0) as u32,
            latency_ms,
            finish_reason: FinishReason::Stop,
        })
    }

    async fn health_check(&self) -> bool {
        self.api_key.is_some()
    }

    fn is_configured(&self) -> bool {
        self.api_key.is_some() && !self.api_key.as_ref().unwrap().is_empty()
    }
}

// ── Concrete Provider: GPT-4 (future integration) ────────────────────────────

pub struct GptProvider {
    api_key: Option<String>,
    base_url: String,
    model_name: String,
    http: reqwest::Client,
}

impl GptProvider {
    pub fn new(api_key: Option<String>, http: reqwest::Client) -> Self {
        Self {
            api_key,
            base_url: "https://api.openai.com/v1".to_string(),
            model_name: "gpt-4o".to_string(),
            http,
        }
    }
}

#[async_trait]
impl ModelProvider for GptProvider {
    fn id(&self) -> &str {
        "gpt-4o"
    }

    fn name(&self) -> &str {
        "GPT-4o"
    }

    fn capabilities(&self) -> ModelCapabilities {
        ModelCapabilities {
            max_context_tokens: 128000,
            max_output_tokens: 16384,
            supports_reasoning: true,
            supports_structured_output: true,
            supports_tool_use: true,
            supports_multimodal: true,
            cost_per_million_input: 2.50,
            cost_per_million_output: 10.00,
            latency_tier: "medium".to_string(),
            quality_tier: "excellent".to_string(),
            specializations: vec!["reasoning".to_string(), "multimodal".to_string(), "tool_use".to_string()],
        }
    }

    async fn infer(&self, request: &InferenceRequest) -> Result<InferenceResponse, ProviderError> {
        let api_key = self
            .api_key
            .as_ref()
            .ok_or_else(|| ProviderError::AuthFailed("No OpenAI API key configured".to_string()))?;

        let url = format!("{}/chat/completions", self.base_url);
        let body = serde_json::json!({
            "model": self.model_name,
            "messages": [
                if let Some(ref sys) = request.system_prompt {
                    serde_json::json!({"role": "system", "content": sys})
                } else {
                    serde_json::json!({"role": "system", "content": "You are a helpful assistant."})
                },
                {"role": "user", "content": request.prompt}
            ],
            "max_tokens": request.max_tokens.unwrap_or(4096),
            "temperature": request.temperature.unwrap_or(0.7),
        });

        let start = std::time::Instant::now();
        let response = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .json(&body)
            .send()
            .await
            .map_err(|e| ProviderError::Internal(format!("HTTP error: {}", e)))?;

        let status = response.status();
        if status == 401 || status == 403 {
            return Err(ProviderError::AuthFailed(format!("HTTP {}", status)));
        }
        if status == 429 {
            return Err(ProviderError::RateLimited("Rate limited by OpenAI".to_string()));
        }
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(ProviderError::Internal(format!("HTTP {}: {}", status, body)));
        }

        let latency_ms = start.elapsed().as_millis() as u64;
        let resp: serde_json::Value = response.json().await
            .map_err(|e| ProviderError::Internal(format!("Parse error: {}", e)))?;

        let content = resp["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("")
            .to_string();

        Ok(InferenceResponse {
            content,
            model_used: self.model_name.clone(),
            provider_id: "gpt-4o".to_string(),
            tokens_input: resp["usage"]["prompt_tokens"].as_u64().unwrap_or(0) as u32,
            tokens_output: resp["usage"]["completion_tokens"].as_u64().unwrap_or(0) as u32,
            latency_ms,
            finish_reason: FinishReason::Stop,
        })
    }

    async fn health_check(&self) -> bool {
        self.api_key.is_some()
    }

    fn is_configured(&self) -> bool {
        self.api_key.is_some() && !self.api_key.as_ref().unwrap().is_empty()
    }
}

// ── AGI Placeholder Provider ─────────────────────────────────────────────────

/// Placeholder for future AGI-class models.
/// When an AGI model becomes available, implement ModelProvider for it
/// and register it with the registry. The harness doesn't change.
pub struct AgiPlaceholderProvider {
    provider_id: String,
    endpoint: Option<String>,
    capabilities: ModelCapabilities,
}

impl AgiPlaceholderProvider {
    pub fn new(provider_id: String) -> Self {
        Self {
            provider_id,
            endpoint: None,
            capabilities: ModelCapabilities {
                max_context_tokens: 1_000_000,
                max_output_tokens: 100_000,
                supports_reasoning: true,
                supports_structured_output: true,
                supports_tool_use: true,
                supports_multimodal: true,
                cost_per_million_input: 0.0, // unknown
                cost_per_million_output: 0.0,
                latency_tier: "medium".to_string(),
                quality_tier: "agi".to_string(),
                specializations: vec![
                    "reasoning".to_string(),
                    "planning".to_string(),
                    "creative".to_string(),
                    "multimodal".to_string(),
                    "tool_use".to_string(),
                    "social_intelligence".to_string(),
                ],
            },
        }
    }
}

#[async_trait]
impl ModelProvider for AgiPlaceholderProvider {
    fn id(&self) -> &str {
        &self.provider_id
    }

    fn name(&self) -> &str {
        "AGI (placeholder)"
    }

    fn capabilities(&self) -> ModelCapabilities {
        self.capabilities.clone()
    }

    async fn infer(&self, _request: &InferenceRequest) -> Result<InferenceResponse, ProviderError> {
        Err(ProviderError::Unavailable(
            "AGI provider not yet available. This placeholder exists so the harness \
             can route to AGI when it becomes available without code changes."
                .to_string(),
        ))
    }

    async fn health_check(&self) -> bool {
        false // Not available yet
    }

    fn is_configured(&self) -> bool {
        self.endpoint.is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_task_type_routing() {
        // Verify task types are defined
        let tasks = vec![
            TaskType::CreditAnalysis,
            TaskType::MarketAnalysis,
            TaskType::Conversation,
            TaskType::Reasoning,
            TaskType::General,
        ];
        assert_eq!(tasks.len(), 5);
    }

    #[test]
    fn test_model_capabilities_default() {
        let caps = ModelCapabilities::default();
        assert_eq!(caps.max_context_tokens, 4096);
        assert!(!caps.supports_reasoning);
        assert_eq!(caps.quality_tier, "good");
    }

    #[test]
    fn test_agi_placeholder_not_configured() {
        let provider = AgiPlaceholderProvider::new("agi-v1".to_string());
        assert!(!provider.is_configured());
        assert_eq!(provider.id(), "agi-v1");
        assert_eq!(provider.capabilities().quality_tier, "agi");
    }
}
