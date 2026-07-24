use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiRequest {
    pub endpoint: String,
    pub method: String,
    pub headers: HashMap<String, String>,
    pub query_params: HashMap<String, String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiResponse {
    pub status: u16,
    pub body: String,
    pub headers: HashMap<String, String>,
}

pub struct ApiGateway {
    rate_limit: u32,
    requests_this_minute: u32,
}

impl ApiGateway {
    pub fn new(rate_limit: u32) -> Self {
        Self { rate_limit, requests_this_minute: 0 }
    }

    pub fn authenticate(&self, token: &str) -> bool {
        // In production: verify JWT token
        !token.is_empty()
    }

    pub fn rate_limit(&mut self) -> bool {
        self.requests_this_minute += 1;
        self.requests_this_minute <= self.rate_limit
    }

    pub fn route(&self, request: &ApiRequest) -> ApiResponse {
        match request.endpoint.as_str() {
            "/api/v1/health" => ApiResponse { status: 200, body: "{\"status\":\"ok\"}".to_string(), headers: HashMap::new() },
            "/api/v1/intelligence" => ApiResponse { status: 200, body: "{\"data\":\"intelligence\"}".to_string(), headers: HashMap::new() },
            _ => ApiResponse { status: 404, body: "{\"error\":\"not found\"}".to_string(), headers: HashMap::new() },
        }
    }
}
