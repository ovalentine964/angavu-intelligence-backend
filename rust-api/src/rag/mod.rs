// =============================================================================
// Angavu Intelligence — RAG Module
// Retrieval-Augmented Generation integration for credit scoring,
// market intelligence, and health/insurance recommendations.
//
// Architecture:
//   Rust API ──HTTP──▶ Python RAG Service (FastAPI)
//                          ├── pgvector (vector store)
//                          ├── NVIDIA NIM (embeddings + reranker)
//                          └── LLM (generation)
//
// The Rust client makes HTTP calls to the Python RAG service,
// which handles the full RAG pipeline (embed → retrieve → rerank → generate).
// =============================================================================

pub mod client;
pub mod credit_context;
pub mod health_context;
pub mod market_context;
pub mod types;

pub use client::RagClient;
pub use types::*;
