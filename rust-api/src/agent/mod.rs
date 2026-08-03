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

pub mod autonomous;
pub mod function_calling;
pub mod memory;
pub mod tool_registry;

// Re-export key types for convenience
pub use autonomous::{AgentConfig, AgentResult, AgentState, AgentTask, AutonomousAgent};
pub use autonomous::{CreditDecisionAgent, LlmClientAdapter, MarketIntelligenceAgent};
pub use function_calling::{FunctionCallParser, FunctionCallingEngine, LlmAction};
pub use memory::{AgentMemory, LongTermMemory, MemoryConfig, ShortTermMemory, WorkingMemory};
pub use tool_registry::{ToolDefinition, ToolError, ToolExecutor, ToolRegistry, ToolResult};
