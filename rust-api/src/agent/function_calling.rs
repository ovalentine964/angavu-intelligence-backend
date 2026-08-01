// =============================================================================
// Angavu Intelligence — Function Calling Engine
// Parses LLM function call responses, validates arguments against JSON Schema,
// executes tools via the registry, and handles errors gracefully.
//
// Architecture:
//   LLM Response → FunctionCallParser → ArgumentValidator → ToolRegistry.execute
//   → ToolResult → ObservationBuilder → back to LLM
//
// Supports OpenAI function calling format (tool_choice, tools array).
// Compatible with DeepSeek, Qwen, GPT-4, and any OpenAI-compatible API.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{debug, error, info, warn};

use super::tool_registry::{ToolRegistry, ToolResult, ToolError};

// ── LLM Message Types (OpenAI Compatible) ───────────────────────────────────

/// Chat completion request with tool definitions
#[derive(Debug, Clone, Serialize)]
pub struct ToolEnabledRequest {
    pub model: String,
    pub messages: Vec<ChatMessage>,
    pub tools: Vec<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_choice: Option<ToolChoice>,
    pub max_tokens: u32,
    pub temperature: f32,
}

/// Tool selection strategy
#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum ToolChoice {
    /// Let the model decide (default)
    Auto,
    /// Model must call a tool
    Required,
    /// Model must not call a tool
    None,
    /// Force a specific tool
    Function { function: FunctionChoice },
}

#[derive(Debug, Clone, Serialize)]
pub struct FunctionChoice {
    pub name: String,
}

/// Chat message in OpenAI format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
}

/// A tool call from the LLM
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub call_type: String,
    pub function: FunctionCall,
}

/// Function call details
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionCall {
    pub name: String,
    pub arguments: String, // JSON string
}

/// Chat completion response
#[derive(Debug, Clone, Deserialize)]
pub struct ChatCompletionResponse {
    pub choices: Vec<ChatChoice>,
    #[serde(default)]
    pub usage: Option<Usage>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ChatChoice {
    pub message: ChatMessageResponse,
    pub finish_reason: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ChatMessageResponse {
    pub role: String,
    pub content: Option<String>,
    #[serde(default)]
    pub tool_calls: Option<Vec<ToolCall>>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Usage {
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
    pub total_tokens: u32,
}

// ── Function Call Parser ─────────────────────────────────────────────────────

/// Parsed function call with validated arguments
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedFunctionCall {
    pub tool_call_id: String,
    pub tool_name: String,
    pub arguments: serde_json::Value,
    pub raw_arguments: String,
}

/// Parse result from an LLM response
#[derive(Debug, Clone)]
pub enum LlmAction {
    /// LLM wants to call one or more tools
    ToolCalls(Vec<ParsedFunctionCall>),
    /// LLM produced a final text response (no tools needed)
    FinalResponse(String),
    /// LLM response was empty or unparseable
    Empty,
}

/// Parses LLM responses to extract function calls
pub struct FunctionCallParser;

impl FunctionCallParser {
    /// Parse an LLM chat completion response into an action
    pub fn parse(response: &ChatCompletionResponse) -> LlmAction {
        let choice = match response.choices.first() {
            Some(c) => c,
            None => return LlmAction::Empty,
        };

        // Check for tool calls
        if let Some(ref tool_calls) = choice.message.tool_calls {
            if !tool_calls.is_empty() {
                let parsed: Vec<ParsedFunctionCall> = tool_calls
                    .iter()
                    .filter_map(|tc| Self::parse_single_tool_call(tc))
                    .collect();

                if !parsed.is_empty() {
                    return LlmAction::ToolCalls(parsed);
                }
            }
        }

        // Check for text response
        if let Some(ref content) = choice.message.content {
            if !content.trim().is_empty() {
                return LlmAction::FinalResponse(content.clone());
            }
        }

        // Check finish reason
        match choice.finish_reason.as_deref() {
            Some("tool_calls") => {
                // LLM indicated tool calls but we couldn't parse them
                warn!("LLM returned finish_reason=tool_calls but no parseable tool calls");
                LlmAction::Empty
            }
            Some("stop") => LlmAction::FinalResponse(
                choice.message.content.clone().unwrap_or_default(),
            ),
            Some("length") => {
                warn!("LLM response truncated due to max_tokens");
                LlmAction::FinalResponse(
                    choice.message.content.clone().unwrap_or_default(),
                )
            }
            _ => LlmAction::Empty,
        }
    }

    /// Parse a single tool call, handling malformed arguments gracefully
    fn parse_single_tool_call(tc: &ToolCall) -> Option<ParsedFunctionCall> {
        // Parse arguments JSON string
        let arguments: serde_json::Value = match serde_json::from_str(&tc.function.arguments) {
            Ok(v) => v,
            Err(e) => {
                // Try to fix common LLM JSON errors
                warn!(
                    tool = %tc.function.name,
                    error = %e,
                    raw_args = %tc.function.arguments,
                    "Failed to parse tool call arguments, attempting repair"
                );

                match Self::repair_json(&tc.function.arguments) {
                    Some(repaired) => repaired,
                    None => {
                        error!(
                            tool = %tc.function.name,
                            "Could not repair malformed arguments, skipping tool call"
                        );
                        return None;
                    }
                }
            }
        };

        Some(ParsedFunctionCall {
            tool_call_id: tc.id.clone(),
            tool_name: tc.function.name.clone(),
            arguments,
            raw_arguments: tc.function.arguments.clone(),
        })
    }

    /// Attempt to repair common JSON errors from LLMs
    fn repair_json(raw: &str) -> Option<serde_json::Value> {
        let trimmed = raw.trim();

        // Handle empty arguments
        if trimmed.is_empty() || trimmed == "{}" {
            return Some(serde_json::json!({}));
        }

        // Try wrapping in braces if missing
        if !trimmed.starts_with('{') {
            let wrapped = format!("{{{}}}", trimmed);
            if let Ok(v) = serde_json::from_str(&wrapped) {
                return Some(v);
            }
        }

        // Try removing trailing commas
        let no_trailing = trimmed
            .replace(",\n}", "\n}")
            .replace(",\r\n}", "\r\n}")
            .replace(",}", "}")
            .replace(",\n]", "\n]")
            .replace(",]", "]");
        if let Ok(v) = serde_json::from_str(&no_trailing) {
            return Some(v);
        }

        // Try single quotes → double quotes
        let double_quoted = trimmed.replace('\'', "\"");
        if let Ok(v) = serde_json::from_str(&double_quoted) {
            return Some(v);
        }

        None
    }
}

// ── Argument Validator ───────────────────────────────────────────────────────

/// Validates tool call arguments against the tool's JSON Schema
pub struct ArgumentValidator;

impl ArgumentValidator {
    /// Validate arguments against a tool definition's schema
    pub fn validate(
        tool_name: &str,
        arguments: &serde_json::Value,
        registry: &ToolRegistry,
    ) -> Result<(), ValidationError> {
        let definition = registry
            .get_definition(tool_name)
            .ok_or_else(|| ValidationError::ToolNotFound(tool_name.to_string()))?;

        // Ensure arguments is an object
        let args_obj = match arguments.as_object() {
            Some(o) => o,
            None => return Err(ValidationError::NotAnObject),
        };

        // Check required fields
        if let Some(ref required) = definition.parameters.required {
            for field in required {
                if !args_obj.contains_key(field) {
                    return Err(ValidationError::MissingRequiredField(field.clone()));
                }
            }
        }

        // Validate no extra fields if additional_properties is false
        if definition.parameters.additional_properties == Some(false) {
            if let Some(props) = definition.parameters.properties.as_object() {
                for key in args_obj.keys() {
                    if !props.contains_key(key) {
                        return Err(ValidationError::UnexpectedField(key.clone()));
                    }
                }
            }
        }

        // Type-check fields against schema
        if let Some(props) = definition.parameters.properties.as_object() {
            for (key, value) in args_obj {
                if let Some(schema) = props.get(key) {
                    Self::check_type(key, value, schema)?;
                }
            }
        }

        Ok(())
    }

    /// Check that a value matches the expected JSON Schema type
    fn check_type(
        field: &str,
        value: &serde_json::Value,
        schema: &serde_json::Value,
    ) -> Result<(), ValidationError> {
        let expected_type = schema.get("type").and_then(|t| t.as_str());

        match expected_type {
            Some("string") => {
                if !value.is_string() {
                    return Err(ValidationError::TypeMismatch {
                        field: field.to_string(),
                        expected: "string".to_string(),
                        got: Self::type_name(value).to_string(),
                    });
                }
                // Check enum constraint
                if let Some(enum_values) = schema.get("enum").and_then(|e| e.as_array()) {
                    let val_str = value.as_str().unwrap_or("");
                    let valid = enum_values.iter().any(|e| e.as_str() == Some(val_str));
                    if !valid {
                        return Err(ValidationError::InvalidEnumValue {
                            field: field.to_string(),
                            value: val_str.to_string(),
                        });
                    }
                }
            }
            Some("integer") => {
                if !value.is_i64() && !value.is_u64() {
                    return Err(ValidationError::TypeMismatch {
                        field: field.to_string(),
                        expected: "integer".to_string(),
                        got: Self::type_name(value).to_string(),
                    });
                }
                // Check min/max
                let num = value.as_i64().unwrap_or(0);
                if let Some(min) = schema.get("minimum").and_then(|m| m.as_i64()) {
                    if num < min {
                        return Err(ValidationError::OutOfRange {
                            field: field.to_string(),
                            value: num.to_string(),
                            constraint: format!("minimum: {}", min),
                        });
                    }
                }
                if let Some(max) = schema.get("maximum").and_then(|m| m.as_i64()) {
                    if num > max {
                        return Err(ValidationError::OutOfRange {
                            field: field.to_string(),
                            value: num.to_string(),
                            constraint: format!("maximum: {}", max),
                        });
                    }
                }
            }
            Some("number") => {
                if !value.is_number() {
                    return Err(ValidationError::TypeMismatch {
                        field: field.to_string(),
                        expected: "number".to_string(),
                        got: Self::type_name(value).to_string(),
                    });
                }
                let num = value.as_f64().unwrap_or(0.0);
                if let Some(min) = schema.get("minimum").and_then(|m| m.as_f64()) {
                    if num < min {
                        return Err(ValidationError::OutOfRange {
                            field: field.to_string(),
                            value: num.to_string(),
                            constraint: format!("minimum: {}", min),
                        });
                    }
                }
                if let Some(max) = schema.get("maximum").and_then(|m| m.as_f64()) {
                    if num > max {
                        return Err(ValidationError::OutOfRange {
                            field: field.to_string(),
                            value: num.to_string(),
                            constraint: format!("maximum: {}", max),
                        });
                    }
                }
            }
            Some("boolean") => {
                if !value.is_boolean() {
                    return Err(ValidationError::TypeMismatch {
                        field: field.to_string(),
                        expected: "boolean".to_string(),
                        got: Self::type_name(value).to_string(),
                    });
                }
            }
            Some("array") => {
                if !value.is_array() {
                    return Err(ValidationError::TypeMismatch {
                        field: field.to_string(),
                        expected: "array".to_string(),
                        got: Self::type_name(value).to_string(),
                    });
                }
                // Check maxItems
                if let (Some(arr), Some(max)) = (value.as_array(), schema.get("maxItems").and_then(|m| m.as_u64())) {
                    if arr.len() as u64 > max {
                        return Err(ValidationError::OutOfRange {
                            field: field.to_string(),
                            value: format!("{} items", arr.len()),
                            constraint: format!("maxItems: {}", max),
                        });
                    }
                }
            }
            Some("object") => {
                if !value.is_object() {
                    return Err(ValidationError::TypeMismatch {
                        field: field.to_string(),
                        expected: "object".to_string(),
                        got: Self::type_name(value).to_string(),
                    });
                }
            }
            _ => {
                // No type constraint, accept anything
            }
        }

        Ok(())
    }

    fn type_name(value: &serde_json::Value) -> &'static str {
        match value {
            serde_json::Value::Null => "null",
            serde_json::Value::Bool(_) => "boolean",
            serde_json::Value::Number(_) => "number",
            serde_json::Value::String(_) => "string",
            serde_json::Value::Array(_) => "array",
            serde_json::Value::Object(_) => "object",
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ValidationError {
    #[error("Tool not found: {0}")]
    ToolNotFound(String),
    #[error("Arguments must be a JSON object")]
    NotAnObject,
    #[error("Missing required field: {0}")]
    MissingRequiredField(String),
    #[error("Unexpected field: {0}")]
    UnexpectedField(String),
    #[error("Type mismatch for field '{field}': expected {expected}, got {got}")]
    TypeMismatch {
        field: String,
        expected: String,
        got: String,
    },
    #[error("Invalid enum value for field '{field}': '{value}'")]
    InvalidEnumValue { field: String, value: String },
    #[error("Out of range for field '{field}': {value} (constraint: {constraint})")]
    OutOfRange {
        field: String,
        value: String,
        constraint: String,
    },
}

// ── Function Calling Engine ──────────────────────────────────────────────────

/// The main engine that orchestrates LLM ↔ Tool interactions
pub struct FunctionCallingEngine {
    registry: Arc<ToolRegistry>,
    http: reqwest::Client,
    /// Maximum tool call iterations before forcing a final answer
    max_iterations: usize,
}

impl FunctionCallingEngine {
    pub fn new(registry: Arc<ToolRegistry>, max_iterations: usize) -> Self {
        Self {
            registry,
            http: reqwest::Client::new(),
            max_iterations,
        }
    }

    /// Execute a parsed function call: validate → execute → return result
    pub async fn execute_call(&self, call: &ParsedFunctionCall) -> ToolCallResult {
        // Validate arguments
        if let Err(e) = ArgumentValidator::validate(&call.tool_name, &call.arguments, &self.registry) {
            warn!(
                tool = %call.tool_name,
                error = %e,
                "Argument validation failed"
            );
            return ToolCallResult {
                tool_call_id: call.tool_call_id.clone(),
                tool_name: call.tool_name.clone(),
                success: false,
                output: serde_json::Value::Null,
                error_message: Some(format!("Validation error: {}", e)),
                execution_ms: 0,
            };
        }

        // Execute via registry
        let result = self.registry.execute_tool(&call.tool_name, call.arguments.clone()).await;

        ToolCallResult {
            tool_call_id: call.tool_call_id.clone(),
            tool_name: call.tool_name.clone(),
            success: result.success,
            output: result.output,
            error_message: result.error,
            execution_ms: result.execution_ms,
        }
    }

    /// Execute multiple function calls (parallel where possible)
    pub async fn execute_calls(&self, calls: &[ParsedFunctionCall]) -> Vec<ToolCallResult> {
        let futures: Vec<_> = calls
            .iter()
            .map(|call| self.execute_call(call))
            .collect();

        futures::future::join_all(futures).await
    }

    /// Build a tool result message for the LLM conversation
    pub fn build_tool_result_message(result: &ToolCallResult) -> ChatMessage {
        let content = if result.success {
            serde_json::to_string_pretty(&result.output)
                .unwrap_or_else(|_| result.output.to_string())
        } else {
            format!(
                "Error: {}",
                result.error_message.as_deref().unwrap_or("Unknown error")
            )
        };

        ChatMessage {
            role: "tool".to_string(),
            content: Some(content),
            tool_calls: None,
            tool_call_id: Some(result.tool_call_id.clone()),
        }
    }

    /// Get the registry for external use
    pub fn registry(&self) -> &Arc<ToolRegistry> {
        &self.registry
    }

    /// Get max iterations setting
    pub fn max_iterations(&self) -> usize {
        self.max_iterations
    }
}

/// Result of a single tool call execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallResult {
    pub tool_call_id: String,
    pub tool_name: String,
    pub success: bool,
    pub output: serde_json::Value,
    pub error_message: Option<String>,
    pub execution_ms: u64,
}

// ── System Prompt Builder ────────────────────────────────────────────────────

/// Builds the system prompt that instructs the LLM on available tools
pub struct SystemPromptBuilder;

impl SystemPromptBuilder {
    /// Build a system prompt with tool descriptions for the LLM
    pub fn build(registry: &ToolRegistry, context: Option<&str>) -> String {
        let tools = registry.all_definitions();
        let mut prompt = String::new();

        prompt.push_str("You are Angavu Intelligence Agent — an autonomous AI system for ");
        prompt.push_str("informal economy intelligence in East Africa.\n\n");

        prompt.push_str("You have access to the following tools. Use them to gather data, ");
        prompt.push_str("analyze markets, assess credit risk, and generate intelligence reports.\n\n");

        prompt.push_str("## Available Tools\n\n");

        for tool in &tools {
            prompt.push_str(&format!("### {}\n", tool.name));
            prompt.push_str(&format!("{}\n", tool.description));
            prompt.push_str(&format!("Category: {:?} | Risk: {:?} | Read-only: {}\n",
                tool.category, tool.risk_level, tool.read_only));

            if let Some(ref required) = tool.parameters.required {
                if !required.is_empty() {
                    prompt.push_str(&format!("Required parameters: {}\n", required.join(", ")));
                }
            }
            prompt.push('\n');
        }

        prompt.push_str("## Guidelines\n");
        prompt.push_str("- Always gather data before making recommendations\n");
        prompt.push_str("- Use multiple tools to cross-validate findings\n");
        prompt.push_str("- Explain your reasoning when presenting results\n");
        prompt.push_str("- Flag low-confidence assessments explicitly\n");
        prompt.push_str("- Respect k-anonymity: never request individual-level data\n");
        prompt.push_str("- For financial decisions, always provide risk assessment\n");

        if let Some(ctx) = context {
            prompt.push_str(&format!("\n## Current Context\n{}\n", ctx));
        }

        prompt
    }

    /// Build a compact prompt for tool selection only (no execution)
    pub fn build_selector_prompt(registry: &ToolRegistry) -> String {
        let tools = registry.all_definitions();
        let mut prompt = String::from(
            "Select the most appropriate tool for the given task. \
             Respond with a JSON object: {\"tool\": \"tool_name\", \"reason\": \"why\"}\n\n"
        );

        for tool in &tools {
            prompt.push_str(&format!("- {}: {}\n", tool.name, tool.description));
        }

        prompt
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::tool_registry::{ToolDefinition, ToolParameterSchema, ToolCategory, ToolRiskLevel};
    use async_trait::async_trait;

    struct MockExecutor;
    #[async_trait]
    impl crate::agent::tool_registry::ToolExecutor for MockExecutor {
        async fn execute(&self, _: serde_json::Value) -> Result<serde_json::Value, ToolError> {
            Ok(serde_json::json!({"result": "ok"}))
        }
        fn validate_input(&self, _: &serde_json::Value) -> Result<(), ToolError> {
            Ok(())
        }
        fn name(&self) -> &str { "mock" }
    }

    fn make_registry() -> Arc<ToolRegistry> {
        let registry = ToolRegistry::new();
        registry.register(
            ToolDefinition {
                name: "test_tool".to_string(),
                description: "A test tool".to_string(),
                parameters: ToolParameterSchema {
                    schema_type: "object".to_string(),
                    properties: serde_json::json!({
                        "name": { "type": "string" },
                        "count": { "type": "integer", "minimum": 0, "maximum": 100 }
                    }),
                    required: Some(vec!["name".to_string()]),
                    additional_properties: Some(false),
                },
                category: ToolCategory::System,
                requires_approval: false,
                risk_level: ToolRiskLevel::Low,
                timeout_secs: 5,
                read_only: true,
            },
            Arc::new(MockExecutor),
        );
        Arc::new(registry)
    }

    #[test]
    fn test_parse_tool_call() {
        let response = ChatCompletionResponse {
            choices: vec![ChatChoice {
                message: ChatMessageResponse {
                    role: "assistant".to_string(),
                    content: None,
                    tool_calls: Some(vec![ToolCall {
                        id: "call_123".to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "test_tool".to_string(),
                            arguments: r#"{"name": "test", "count": 5}"#.to_string(),
                        },
                    }]),
                },
                finish_reason: Some("tool_calls".to_string()),
            }],
            usage: None,
        };

        match FunctionCallParser::parse(&response) {
            LlmAction::ToolCalls(calls) => {
                assert_eq!(calls.len(), 1);
                assert_eq!(calls[0].tool_name, "test_tool");
                assert_eq!(calls[0].arguments["name"], "test");
            }
            _ => panic!("Expected ToolCalls"),
        }
    }

    #[test]
    fn test_parse_final_response() {
        let response = ChatCompletionResponse {
            choices: vec![ChatChoice {
                message: ChatMessageResponse {
                    role: "assistant".to_string(),
                    content: Some("Here is my analysis...".to_string()),
                    tool_calls: None,
                },
                finish_reason: Some("stop".to_string()),
            }],
            usage: None,
        };

        match FunctionCallParser::parse(&response) {
            LlmAction::FinalResponse(text) => {
                assert_eq!(text, "Here is my analysis...");
            }
            _ => panic!("Expected FinalResponse"),
        }
    }

    #[test]
    fn test_validate_missing_required() {
        let registry = make_registry();
        let args = serde_json::json!({"count": 5});
        let result = ArgumentValidator::validate("test_tool", &args, &registry);
        assert!(matches!(result, Err(ValidationError::MissingRequiredField(ref f)) if f == "name"));
    }

    #[test]
    fn test_validate_type_mismatch() {
        let registry = make_registry();
        let args = serde_json::json!({"name": 123});
        let result = ArgumentValidator::validate("test_tool", &args, &registry);
        assert!(matches!(result, Err(ValidationError::TypeMismatch { .. })));
    }

    #[test]
    fn test_validate_out_of_range() {
        let registry = make_registry();
        let args = serde_json::json!({"name": "test", "count": 200});
        let result = ArgumentValidator::validate("test_tool", &args, &registry);
        assert!(matches!(result, Err(ValidationError::OutOfRange { .. })));
    }

    #[test]
    fn test_validate_unexpected_field() {
        let registry = make_registry();
        let args = serde_json::json!({"name": "test", "extra": "bad"});
        let result = ArgumentValidator::validate("test_tool", &args, &registry);
        assert!(matches!(result, Err(ValidationError::UnexpectedField(ref f)) if f == "extra"));
    }

    #[test]
    fn test_validate_success() {
        let registry = make_registry();
        let args = serde_json::json!({"name": "test", "count": 50});
        assert!(ArgumentValidator::validate("test_tool", &args, &registry).is_ok());
    }

    #[test]
    fn test_json_repair_trailing_comma() {
        let raw = r#"{"name": "test", "count": 5,}"#;
        let result = FunctionCallParser::repair_json(raw);
        assert!(result.is_some());
        assert_eq!(result.unwrap()["name"], "test");
    }

    #[test]
    fn test_system_prompt_builder() {
        let registry = make_registry();
        let prompt = SystemPromptBuilder::build(&registry, None);
        assert!(prompt.contains("test_tool"));
        assert!(prompt.contains("A test tool"));
    }
}
