// =============================================================================
// Angavu Intelligence — Hardened LLM Integration
// Replaces fragile Python subprocess with direct HTTP, circuit breaker,
// retry with exponential backoff, and pattern matching fallback
// =============================================================================

pub mod providers;

use anyhow::{anyhow, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

// ── Configuration ────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct LlmConfig {
    pub deepseek_api_key: Option<String>,
    pub qwen_api_key: Option<String>,
    pub deepseek_base_url: String,
    pub qwen_base_url: String,
    pub max_retries: u32,
    pub initial_backoff_ms: u64,
    pub max_backoff_ms: u64,
    pub request_timeout_secs: u64,
    /// Circuit breaker: failures before opening
    pub circuit_breaker_threshold: u32,
    /// Circuit breaker: seconds before half-open
    pub circuit_breaker_recovery_secs: u64,
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            deepseek_api_key: std::env::var("DEEPSEEK_API_KEY").ok(),
            qwen_api_key: std::env::var("QWEN_API_KEY").ok(),
            deepseek_base_url: "https://api.deepseek.com/v1".to_string(),
            qwen_base_url: "https://api.qwen.com/v1".to_string(),
            max_retries: 3,
            initial_backoff_ms: 500,
            max_backoff_ms: 30_000,
            request_timeout_secs: 30,
            circuit_breaker_threshold: 5,
            circuit_breaker_recovery_secs: 60,
        }
    }
}

// ── Circuit Breaker ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
enum CircuitState {
    Closed,    // Normal operation
    Open,      // Failing, reject requests
    HalfOpen,  // Testing recovery
}

pub struct CircuitBreaker {
    state: RwLock<CircuitState>,
    failure_count: AtomicU32,
    last_failure: RwLock<Option<Instant>>,
    threshold: u32,
    recovery_duration: Duration,
}

impl CircuitBreaker {
    pub fn new(threshold: u32, recovery_secs: u64) -> Self {
        Self {
            state: RwLock::new(CircuitState::Closed),
            failure_count: AtomicU32::new(0),
            last_failure: RwLock::new(None),
            threshold,
            recovery_duration: Duration::from_secs(recovery_secs),
        }
    }

    pub async fn is_available(&self) -> bool {
        let state = self.state.read().await;
        match *state {
            CircuitState::Closed => true,
            CircuitState::Open => {
                // Check if recovery time has elapsed
                if let Some(last) = *self.last_failure.read().await {
                    if last.elapsed() >= self.recovery_duration {
                        drop(state);
                        let mut state = self.state.write().await;
                        *state = CircuitState::HalfOpen;
                        info!("Circuit breaker: Open → HalfOpen (testing recovery)");
                        return true;
                    }
                }
                false
            }
            CircuitState::HalfOpen => true,
        }
    }

    pub async fn record_success(&self) {
        let prev_count = self.failure_count.swap(0, Ordering::SeqCst);
        let mut state = self.state.write().await;
        if *state == CircuitState::HalfOpen {
            info!("Circuit breaker: HalfOpen → Closed (recovered)");
        }
        *state = CircuitState::Closed;
        if prev_count > 0 {
            debug!("Circuit breaker: reset failure count from {}", prev_count);
        }
    }

    pub async fn record_failure(&self) {
        let count = self.failure_count.fetch_add(1, Ordering::SeqCst) + 1;
        *self.last_failure.write().await = Some(Instant::now());

        if count >= self.threshold {
            let mut state = self.state.write().await;
            *state = CircuitState::Open;
            warn!(
                "Circuit breaker: Closed → Open ({} failures >= threshold {})",
                count, self.threshold
            );
        }
    }

    #[cfg(test)]
    pub async fn state(&self) -> CircuitState {
        self.state.read().await.clone()
    }
}

// ── LLM Request/Response Types ───────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatMessage>,
    max_tokens: u32,
    temperature: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
}

#[derive(Debug, Deserialize)]
struct ChatChoice {
    message: ChatMessage,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmResponse {
    pub response: String,
    pub model: String,
    pub source: String,  // "llm" or "fallback"
    pub latency_ms: u64,
}

// ── LLM Client ───────────────────────────────────────────────────────────────

pub struct LlmClient {
    http: Client,
    config: LlmConfig,
    deepseek_breaker: Arc<CircuitBreaker>,
    qwen_breaker: Arc<CircuitBreaker>,
    requests_total: AtomicU64,
    failures_total: AtomicU64,
    fallbacks_total: AtomicU64,
}

impl LlmClient {
    pub fn new(config: LlmConfig) -> Result<Self> {
        let http = Client::builder()
            .timeout(Duration::from_secs(config.request_timeout_secs))
            .connect_timeout(Duration::from_secs(10))
            .pool_max_idle_per_host(4)
            .build()?;

        let deepseek_breaker = Arc::new(CircuitBreaker::new(
            config.circuit_breaker_threshold,
            config.circuit_breaker_recovery_secs,
        ));
        let qwen_breaker = Arc::new(CircuitBreaker::new(
            config.circuit_breaker_threshold,
            config.circuit_breaker_recovery_secs,
        ));

        Ok(Self {
            http,
            config,
            deepseek_breaker,
            qwen_breaker,
            requests_total: AtomicU64::new(0),
            failures_total: AtomicU64::new(0),
            fallbacks_total: AtomicU64::new(0),
        })
    }

    /// Query DeepSeek Reasoner for complex credit analysis
    pub async fn query_deepseek_reasoner(&self, prompt: &str) -> LlmResponse {
        self.query_with_fallback(
            "deepseek-reasoner",
            prompt,
            &self.config.deepseek_api_key,
            &self.config.deepseek_base_url,
            self.deepseek_breaker.clone(),
        )
        .await
    }

    /// Query DeepSeek Chat for conversational responses
    pub async fn query_deepseek_chat(&self, prompt: &str) -> LlmResponse {
        self.query_with_fallback(
            "deepseek-chat",
            prompt,
            &self.config.deepseek_api_key,
            &self.config.deepseek_base_url,
            self.deepseek_breaker.clone(),
        )
        .await
    }

    /// Query Qwen 7B for cloud inference
    pub async fn query_qwen(&self, prompt: &str) -> LlmResponse {
        self.query_with_fallback(
            "qwen-7b",
            prompt,
            &self.config.qwen_api_key,
            &self.config.qwen_base_url,
            self.qwen_breaker.clone(),
        )
        .await
    }

    /// Core query method with circuit breaker, retry, and fallback
    async fn query_with_fallback(
        &self,
        model: &str,
        prompt: &str,
        api_key: &Option<String>,
        base_url: &str,
        breaker: Arc<CircuitBreaker>,
    ) -> LlmResponse {
        self.requests_total.fetch_add(1, Ordering::Relaxed);
        let start = Instant::now();

        // Check circuit breaker
        if !breaker.is_available().await {
            warn!("Circuit breaker OPEN for {}, using fallback", model);
            self.fallbacks_total.fetch_add(1, Ordering::Relaxed);
            return LlmResponse {
                response: self.pattern_match_fallback(prompt),
                model: model.to_string(),
                source: "fallback".to_string(),
                latency_ms: start.elapsed().as_millis() as u64,
            };
        }

        // Check API key
        let key = match api_key {
            Some(k) if !k.is_empty() => k.clone(),
            _ => {
                warn!("No API key for {}, using fallback", model);
                self.fallbacks_total.fetch_add(1, Ordering::Relaxed);
                return LlmResponse {
                    response: self.pattern_match_fallback(prompt),
                    model: model.to_string(),
                    source: "fallback".to_string(),
                    latency_ms: start.elapsed().as_millis() as u64,
                };
            }
        };

        // Retry with exponential backoff
        let mut backoff = Duration::from_millis(self.config.initial_backoff_ms);
        let mut last_error = String::new();

        for attempt in 1..=self.config.max_retries {
            match self.call_llm_api(model, prompt, &key, base_url).await {
                Ok(response) => {
                    breaker.record_success().await;
                    debug!(
                        "LLM call succeeded: model={}, attempt={}, latency={}ms",
                        model,
                        attempt,
                        start.elapsed().as_millis()
                    );
                    return LlmResponse {
                        response,
                        model: model.to_string(),
                        source: "llm".to_string(),
                        latency_ms: start.elapsed().as_millis() as u64,
                    };
                }
                Err(e) => {
                    last_error = e.to_string();
                    warn!(
                        "LLM call failed: model={}, attempt={}, error={}, backoff={}ms",
                        model, attempt, last_error, backoff.as_millis()
                    );

                    // Don't retry on auth errors (401/403)
                    if last_error.contains("401") || last_error.contains("403") {
                        break;
                    }

                    if attempt < self.config.max_retries {
                        tokio::time::sleep(backoff).await;
                        backoff = std::cmp::min(
                            backoff * 2,
                            Duration::from_millis(self.config.max_backoff_ms),
                        );
                    }
                }
            }
        }

        // All retries failed
        breaker.record_failure().await;
        self.failures_total.fetch_add(1, Ordering::Relaxed);
        self.fallbacks_total.fetch_add(1, Ordering::Relaxed);

        error!(
            "All {} retries exhausted for {}, using fallback. Last error: {}",
            self.config.max_retries, model, last_error
        );

        LlmResponse {
            response: self.pattern_match_fallback(prompt),
            model: model.to_string(),
            source: "fallback".to_string(),
            latency_ms: start.elapsed().as_millis() as u64,
        }
    }

    /// Direct HTTP call to LLM API (replaces Python subprocess)
    async fn call_llm_api(
        &self,
        model: &str,
        prompt: &str,
        api_key: &str,
        base_url: &str,
    ) -> Result<String> {
        let url = format!("{}/chat/completions", base_url);

        let request = ChatRequest {
            model: model.to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: prompt.to_string(),
            }],
            max_tokens: 2048,
            temperature: 0.7,
        };

        let response = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .header("Content-Type", "application/json")
            .json(&request)
            .send()
            .await
            .map_err(|e| anyhow!("HTTP request failed: {}", e))?;

        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow!("LLM API error {}: {}", status, body));
        }

        let chat_response: ChatResponse = response
            .json()
            .await
            .map_err(|e| anyhow!("Failed to parse LLM response: {}", e))?;

        chat_response
            .choices
            .first()
            .map(|c| c.message.content.clone())
            .ok_or_else(|| anyhow!("Empty response from LLM"))
    }

    /// Pattern matching fallback when LLM is unavailable
    /// Provides rule-based credit analysis using known heuristics
    fn pattern_match_fallback(&self, prompt: &str) -> String {
        let prompt_lower = prompt.to_lowercase();

        // Credit scoring fallback
        if prompt_lower.contains("credit") || prompt_lower.contains("score") || prompt_lower.contains("risk") {
            return serde_json::json!({
                "analysis": "Credit assessment generated via rule-based fallback (LLM unavailable)",
                "method": "pattern_matching",
                "factors": {
                    "transaction_volume": "Evaluated against sector benchmarks",
                    "consistency": "Active days ratio threshold: >0.6 preferred",
                    "volatility": "Revenue CV < 0.5 indicates stability",
                    "recency": "Last transaction within 30 days preferred"
                },
                "recommendation": "Score based on logistic regression model with domain-informed weights",
                "confidence": 0.6,
                "note": "Lower confidence than LLM-enhanced analysis. Retry later for full assessment."
            }).to_string();
        }

        // Market analysis fallback
        if prompt_lower.contains("market") || prompt_lower.contains("trend") {
            return serde_json::json!({
                "analysis": "Market analysis via cached patterns (LLM unavailable)",
                "method": "pattern_matching",
                "factors": ["seasonality_adjusted", "regional_benchmark", "sector_trend"],
                "recommendation": "Use historical averages with 20% safety margin",
                "confidence": 0.5,
                "note": "LLM service temporarily unavailable. Using statistical fallback."
            }).to_string();
        }

        // Generic fallback
        serde_json::json!({
            "analysis": "Request processed via pattern matching (LLM service unavailable)",
            "method": "fallback",
            "recommendation": "Retry request when LLM service recovers",
            "confidence": 0.4,
            "note": "This response was generated by the rule-based fallback engine."
        }).to_string()
    }

    /// Get client metrics for monitoring
    pub fn metrics(&self) -> LlmMetrics {
        LlmMetrics {
            requests_total: self.requests_total.load(Ordering::Relaxed),
            failures_total: self.failures_total.load(Ordering::Relaxed),
            fallbacks_total: self.fallbacks_total.load(Ordering::Relaxed),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct LlmMetrics {
    pub requests_total: u64,
    pub failures_total: u64,
    pub fallbacks_total: u64,
}

// ── Model-Agnostic Engine ─────────────────────────────────────────────────────

/// Model-agnostic LLM engine that routes requests to the best available provider.
/// This is the primary interface for all LLM calls in the system.
/// "Harness is permanent, model is swappable."
pub struct ModelAgnosticEngine {
    registry: providers::ModelRegistry,
    fallback_engine: LlmClient,
}

impl ModelAgnosticEngine {
    pub fn new(config: LlmConfig) -> Result<Self> {
        let fallback_engine = LlmClient::new(config)?;
        Ok(Self {
            registry: providers::ModelRegistry::new(),
            fallback_engine,
        })
    }

    /// Register a model provider
    pub async fn register_provider(&self, provider: std::sync::Arc<dyn providers::ModelProvider>) {
        self.registry.register(provider).await;
    }

    /// Set routing preferences for a task type
    pub async fn set_routing(&self, task_type: providers::TaskType, provider_order: Vec<String>) {
        self.registry.set_routing(task_type, provider_order).await;
    }

    /// Set the default provider
    pub async fn set_default_provider(&self, provider_id: String) {
        self.registry.set_default(provider_id).await;
    }

    /// Query using the best available provider for the task.
    /// Falls back to the legacy LlmClient if no provider is available.
    pub async fn query(&self, request: &providers::InferenceRequest) -> LlmResponse {
        // Try model-agnostic path first
        if let Some(provider) = self.registry.resolve(request.task_type).await {
            match provider.infer(request).await {
                Ok(response) => {
                    return LlmResponse {
                        response: response.content,
                        model: response.model_used,
                        source: format!("provider:{}", response.provider_id),
                        latency_ms: response.latency_ms,
                    };
                }
                Err(e) => {
                    tracing::warn!(
                        "Provider {} failed for task {:?}: {}. Falling back.",
                        provider.id(),
                        request.task_type,
                        e
                    );
                }
            }
        }

        // Fall back to legacy LlmClient
        self.fallback_engine.query_deepseek_chat(&request.prompt).await
    }

    /// List all registered providers
    pub async fn list_providers(&self) -> Vec<providers::ProviderInfo> {
        self.registry.list_providers().await
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_circuit_breaker_opens_after_threshold() {
        let cb = CircuitBreaker::new(3, 60);

        // Should start closed
        assert!(cb.is_available().await);

        // Record failures up to threshold
        cb.record_failure().await;
        assert!(cb.is_available().await); // 1 < 3
        cb.record_failure().await;
        assert!(cb.is_available().await); // 2 < 3
        cb.record_failure().await;

        // Should now be open
        assert!(!cb.is_available().await);
    }

    #[tokio::test]
    async fn test_circuit_breaker_resets_on_success() {
        let cb = CircuitBreaker::new(3, 60);

        cb.record_failure().await;
        cb.record_failure().await;
        cb.record_success().await; // Reset

        assert_eq!(cb.failure_count.load(Ordering::SeqCst), 0);
        assert!(cb.is_available().await);
    }

    #[tokio::test]
    async fn test_fallback_pattern_matching() {
        let config = LlmConfig {
            deepseek_api_key: None,
            qwen_api_key: None,
            ..Default::default()
        };
        let client = LlmClient::new(config).unwrap();

        let response = client.query_deepseek_reasoner("Analyze credit score for worker").await;
        assert_eq!(response.source, "fallback");
        assert!(response.response.contains("pattern_matching"));
    }

    #[tokio::test]
    async fn test_llm_metrics() {
        let config = LlmConfig {
            deepseek_api_key: None,
            ..Default::default()
        };
        let client = LlmClient::new(config).unwrap();

        client.query_deepseek_reasoner("test").await;
        let metrics = client.metrics();
        assert_eq!(metrics.requests_total, 1);
        assert_eq!(metrics.fallbacks_total, 1);
    }
}
