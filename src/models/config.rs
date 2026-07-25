use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub server: ServerConfig,
    pub database: DatabaseConfig,
    pub redis: RedisConfig,
    pub clickhouse: ClickHouseConfig,
    pub security: SecurityConfig,
    pub llm: LLMConfig,
    pub superagent: SuperagentConfig,
    pub metrics: MetricsConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerConfig {
    pub host: String,
    pub port: u16,
    pub workers: usize,
    pub max_connections: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseConfig {
    pub url: String,
    pub max_connections: u32,
    pub min_connections: u32,
    pub connect_timeout: u64,
    pub idle_timeout: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RedisConfig {
    pub url: String,
    pub pool_size: u32,
    pub cluster: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClickHouseConfig {
    pub url: String,
    pub database: String,
    pub user: String,
    pub password: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityConfig {
    pub jwt_secret: String,
    pub jwt_expiration: u64,
    pub encryption_key: String,
    pub post_quantum_enabled: bool,
    pub kem_algorithm: String,
    pub signature_algorithm: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMConfig {
    pub deepseek_api_key: String,
    pub deepseek_model: String,
    pub qwen_api_key: String,
    pub qwen_model: String,
    pub python_path: String,
    pub max_tokens: u32,
    pub temperature: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SuperagentConfig {
    pub ooda_cycle_interval_ms: u64,
    pub max_concurrent_tasks: usize,
    pub memory_ttl_hours: u64,
    pub federated_learning_enabled: bool,
    pub differential_privacy_epsilon: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricsConfig {
    pub enabled: bool,
    pub port: u16,
    pub path: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            server: ServerConfig {
                host: "0.0.0.0".to_string(),
                port: 8080,
                workers: num_cpus::get(),
                max_connections: 10000,
            },
            database: DatabaseConfig {
                url: "postgres://angavu:angavu@localhost:5432/angavu".to_string(),
                max_connections: 100,
                min_connections: 10,
                connect_timeout: 30,
                idle_timeout: 600,
            },
            redis: RedisConfig {
                url: "redis://localhost:6379".to_string(),
                pool_size: 100,
                cluster: false,
            },
            clickhouse: ClickHouseConfig {
                url: "http://localhost:8123".to_string(),
                database: "angavu".to_string(),
                user: "default".to_string(),
                password: String::new(),
            },
            security: SecurityConfig {
                jwt_secret: "change-me-in-production".to_string(),
                jwt_expiration: 3600,
                encryption_key: "change-me-32-bytes-key-here!!!!".to_string(),
                post_quantum_enabled: true,
                kem_algorithm: "ML-KEM-768".to_string(),
                signature_algorithm: "Ed25519".to_string(),
            },
            llm: LLMConfig {
                deepseek_api_key: String::new(),
                deepseek_model: "deepseek-reasoner".to_string(),
                qwen_api_key: String::new(),
                qwen_model: "qwen-max".to_string(),
                python_path: "python3".to_string(),
                max_tokens: 4096,
                temperature: 0.7,
            },
            superagent: SuperagentConfig {
                ooda_cycle_interval_ms: 1000,
                max_concurrent_tasks: 100,
                memory_ttl_hours: 720,
                federated_learning_enabled: true,
                differential_privacy_epsilon: 1.0,
            },
            metrics: MetricsConfig {
                enabled: true,
                port: 9090,
                path: "/metrics".to_string(),
            },
        }
    }
}
