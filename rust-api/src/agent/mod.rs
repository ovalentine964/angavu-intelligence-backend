// =============================================================================
// Angavu Intelligence — Agent Framework
// LLM-driven tool use and autonomous OODA reasoning.
//
// Components:
//   - tool_registry: 26 callable tools with JSON Schema definitions
//   - function_calling: LLM function call parsing, validation, execution
//   - autonomous: ReAct-pattern autonomous OODA agent
//   - memory: Three-tier memory system (short-term, working, long-term)
//
// Architecture:
//   LLM ←→ FunctionCallingEngine ←→ ToolRegistry
//              ↕
//         AutonomousAgent (OODA + ReAct)
//              ↕
//          AgentMemory (3 tiers)
// =============================================================================

pub mod tool_registry;
pub mod function_calling;
pub mod autonomous;
pub mod memory;

// Re-export key types for convenience
pub use tool_registry::{ToolRegistry, ToolDefinition, ToolResult, ToolExecutor, ToolError};
pub use function_calling::{FunctionCallingEngine, FunctionCallParser, LlmAction};
pub use autonomous::{AutonomousAgent, AgentConfig, AgentTask, AgentResult, AgentState};
pub use autonomous::{CreditDecisionAgent, MarketIntelligenceAgent, LlmClientAdapter};
pub use memory::{AgentMemory, MemoryConfig, ShortTermMemory, WorkingMemory, LongTermMemory};
