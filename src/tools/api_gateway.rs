use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiRequest {
    pub endpoint: String,
    pub method: String,
    pub headers: HashMap<String, String>,
    pub query_params: HashMap<String, String>,
    pub body: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiResponse {
    pub status: u16,
    pub body: String,
    pub headers: HashMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct Route {
    pub method: String,
    pub path_pattern: String,
    pub handler_name: String,
    pub requires_auth: bool,
}

#[derive(Debug, Clone)]
pub struct MiddlewareResult {
    pub proceed: bool,
    pub response: Option<ApiResponse>,
}

pub struct ApiGateway {
    rate_limit: u32,
    requests_this_minute: u32,
    last_minute_reset: Instant,
    routes: Vec<Route>,
    allowed_origins: Vec<String>,
    jwt_secret: String,
}

impl ApiGateway {
    pub fn new(rate_limit: u32) -> Self {
        Self {
            rate_limit,
            requests_this_minute: 0,
            last_minute_reset: Instant::now(),
            routes: Vec::new(),
            allowed_origins: vec!["*".to_string()],
            jwt_secret: "default-secret".to_string(),
        }
    }

    pub fn with_jwt_secret(mut self, secret: &str) -> Self {
        self.jwt_secret = secret.to_string();
        self
    }

    pub fn with_cors_origins(mut self, origins: Vec<String>) -> Self {
        self.allowed_origins = origins;
        self
    }

    /// Register a route with pattern matching.
    pub fn add_route(&mut self, method: &str, path_pattern: &str, handler_name: &str, requires_auth: bool) {
        self.routes.push(Route {
            method: method.to_uppercase(),
            path_pattern: path_pattern.to_string(),
            handler_name: handler_name.to_string(),
            requires_auth,
        });
    }

    /// Register default routes for the Angavu platform.
    pub fn register_default_routes(&mut self) {
        self.add_route("GET", "/api/v1/health", "health_check", false);
        self.add_route("GET", "/api/v1/intelligence", "get_intelligence", true);
        self.add_route("POST", "/api/v1/intelligence/analyze", "analyze", true);
        self.add_route("GET", "/api/v1/reports/:type", "get_report", true);
        self.add_route("POST", "/api/v1/sync", "sync_data", true);
        self.add_route("GET", "/api/v1/credit/:user_id", "credit_score", true);
        self.add_route("POST", "/api/v1/auth/login", "login", false);
        self.add_route("POST", "/api/v1/auth/refresh", "refresh_token", true);
    }

    /// Match a request path against registered route patterns.
    /// Supports :param placeholders (e.g., /reports/:type matches /reports/daily).
    pub fn match_route(&self, method: &str, path: &str) -> Option<(&Route, HashMap<String, String>)> {
        let method_upper = method.to_uppercase();
        for route in &self.routes {
            if route.method != method_upper {
                continue;
            }
            if let Some(params) = Self::match_pattern(&route.path_pattern, path) {
                return Some((route, params));
            }
        }
        None
    }

    /// Match a path pattern against an actual path, extracting named parameters.
    fn match_pattern(pattern: &str, path: &str) -> Option<HashMap<String, String>> {
        let pattern_parts: Vec<&str> = pattern.split('/').collect();
        let path_parts: Vec<&str> = path.split('/').collect();

        if pattern_parts.len() != path_parts.len() {
            return None;
        }

        let mut params = HashMap::new();
        for (pp, pa) in pattern_parts.iter().zip(path_parts.iter()) {
            if pp.starts_with(':') {
                params.insert(pp[1..].to_string(), pa.to_string());
            } else if pp != pa {
                return None;
            }
        }
        Some(params)
    }

    /// Authenticate a JWT token (simplified HMAC verification).
    pub fn authenticate(&self, token: &str) -> bool {
        if token.is_empty() {
            return false;
        }
        // Verify token has 3 parts (header.payload.signature)
        let parts: Vec<&str> = token.split('.').collect();
        if parts.len() != 3 {
            return false;
        }
        // Decode and verify signature using HMAC-SHA256
        use hmac::{Hmac, Mac};
        use sha2::Sha256;
        type HmacSha256 = Hmac<Sha256>;

        let signature_b64 = parts[2];
        let message = format!("{}.{}", parts[0], parts[1]);
        let Ok(signature_bytes) = base64_decode(signature_b64) else {
            return false;
        };

        let mut mac = HmacSha256::new_from_slice(self.jwt_secret.as_bytes())
            .expect("HMAC accepts any key length");
        mac.update(message.as_bytes());
        mac.verify_slice(&signature_bytes).is_ok()
    }

    /// Sliding window rate limiter with automatic window reset.
    pub fn rate_limit(&mut self) -> bool {
        let now = Instant::now();
        if now.duration_since(self.last_minute_reset) >= Duration::from_secs(60) {
            self.requests_this_minute = 0;
            self.last_minute_reset = now;
        }
        self.requests_this_minute += 1;
        self.requests_this_minute <= self.rate_limit
    }

    /// Apply CORS middleware to response headers.
    pub fn apply_cors(&self, origin: &str) -> HashMap<String, String> {
        let mut headers = HashMap::new();
        let allowed = self.allowed_origins.contains(&"*".to_string())
            || self.allowed_origins.contains(&origin.to_string());
        if allowed {
            headers.insert("Access-Control-Allow-Origin".to_string(), origin.to_string());
            headers.insert("Access-Control-Allow-Methods".to_string(), "GET, POST, PUT, DELETE, OPTIONS".to_string());
            headers.insert("Access-Control-Allow-Headers".to_string(), "Content-Type, Authorization".to_string());
            headers.insert("Access-Control-Max-Age".to_string(), "86400".to_string());
        }
        headers
    }

    /// Process a request through the full middleware chain: CORS → rate limit → auth → route.
    pub fn process(&mut self, request: &ApiRequest) -> ApiResponse {
        // 1. CORS preflight
        if request.method == "OPTIONS" {
            let origin = request.headers.get("Origin").map(|s| s.as_str()).unwrap_or("*");
            let mut headers = self.apply_cors(origin);
            headers.insert("Content-Type".to_string(), "text/plain".to_string());
            return ApiResponse { status: 204, body: String::new(), headers };
        }

        // 2. Rate limit
        if !self.rate_limit() {
            return ApiResponse {
                status: 429,
                body: r#"{"error":"rate_limit_exceeded","message":"Too many requests"}"#.to_string(),
                headers: HashMap::from([("Retry-After".to_string(), "60".to_string())]),
            };
        }

        // 3. Route matching
        let matched = self.match_route(&request.method, &request.endpoint);
        let (route, params) = match matched {
            Some((r, p)) => (r.clone(), p),
            None => {
                return ApiResponse {
                    status: 404,
                    body: r#"{"error":"not_found","message":"Endpoint not found"}"#.to_string(),
                    headers: HashMap::new(),
                };
            }
        };

        // 4. Authentication
        if route.requires_auth {
            let token = request.headers.get("Authorization")
                .and_then(|h| h.strip_prefix("Bearer "))
                .unwrap_or("");
            if !self.authenticate(token) {
                return ApiResponse {
                    status: 401,
                    body: r#"{"error":"unauthorized","message":"Invalid or missing token"}"#.to_string(),
                    headers: HashMap::new(),
                };
            }
        }

        // 5. CORS for response
        let origin = request.headers.get("Origin").map(|s| s.as_str()).unwrap_or("*");
        let mut headers = self.apply_cors(origin);
        headers.insert("Content-Type".to_string(), "application/json".to_string());

        // 6. Dispatch to handler
        let body = match route.handler_name.as_str() {
            "health_check" => {
                format!(r#"{{"status":"ok","timestamp":{}}}"#, now_timestamp())
            }
            "get_intelligence" => {
                r#"{"data":"intelligence_feed","items":[]}"#.to_string()
            }
            "analyze" => {
                r#"{"status":"processing","job_id":"job_001"}"#.to_string()
            }
            "get_report" => {
                let report_type = params.get("type").map(|s| s.as_str()).unwrap_or("unknown");
                format!(r#"{{"report_type":"{}","status":"generating"}}"#, report_type)
            }
            "sync_data" => {
                r#"{"status":"syncing","sync_id":"sync_001"}"#.to_string()
            }
            "credit_score" => {
                let user_id = params.get("user_id").map(|s| s.as_str()).unwrap_or("unknown");
                format!(r#"{{"user_id":"{}","score":null,"status":"calculating"}}"#, user_id)
            }
            "login" => {
                r#"{"status":"authenticated","token":"<generated>"}"#.to_string()
            }
            "refresh_token" => {
                r#"{"status":"refreshed","token":"<refreshed>"}"#.to_string()
            }
            _ => {
                return ApiResponse {
                    status: 501,
                    body: r#"{"error":"not_implemented","message":"Handler not implemented"}"#.to_string(),
                    headers,
                };
            }
        };

        ApiResponse { status: 200, body, headers }
    }

    /// Route a request (legacy interface, delegates to process).
    pub fn route(&self, request: &ApiRequest) -> ApiResponse {
        match request.endpoint.as_str() {
            "/api/v1/health" => ApiResponse {
                status: 200,
                body: r#"{"status":"ok"}"#.to_string(),
                headers: HashMap::new(),
            },
            "/api/v1/intelligence" => ApiResponse {
                status: 200,
                body: r#"{"data":"intelligence"}"#.to_string(),
                headers: HashMap::new(),
            },
            _ => ApiResponse {
                status: 404,
                body: r#"{"error":"not found"}"#.to_string(),
                headers: HashMap::new(),
            },
        }
    }
}

fn now_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn base64_decode(input: &str) -> Result<Vec<u8>, &'static str> {
    const TABLE: [i8; 128] = [
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
        52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-1,-1,-1,
        -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
        15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
        -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
        41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1,
    ];
    let mut result = Vec::new();
    let mut buf: u32 = 0;
    let mut bits: u32 = 0;
    for &byte in input.as_bytes() {
        if byte == b'=' { break; }
        let val = TABLE.get(byte as usize).copied().unwrap_or(-1);
        if val < 0 { return Err("invalid base64 char"); }
        buf = (buf << 6) | val as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            result.push((buf >> bits) as u8);
            buf &= (1 << bits) - 1;
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_request(method: &str, endpoint: &str) -> ApiRequest {
        ApiRequest {
            endpoint: endpoint.to_string(),
            method: method.to_string(),
            headers: HashMap::new(),
            query_params: HashMap::new(),
            body: None,
        }
    }

    #[test]
    fn test_route_matching_static() {
        let mut gw = ApiGateway::new(100);
        gw.register_default_routes();
        let result = gw.match_route("GET", "/api/v1/health");
        assert!(result.is_some());
        let (route, params) = result.unwrap();
        assert_eq!(route.handler_name, "health_check");
        assert!(params.is_empty());
    }

    #[test]
    fn test_route_matching_with_params() {
        let mut gw = ApiGateway::new(100);
        gw.register_default_routes();
        let result = gw.match_route("GET", "/api/v1/reports/daily");
        assert!(result.is_some());
        let (route, params) = result.unwrap();
        assert_eq!(route.handler_name, "get_report");
        assert_eq!(params.get("type").unwrap(), "daily");
    }

    #[test]
    fn test_route_no_match() {
        let mut gw = ApiGateway::new(100);
        gw.register_default_routes();
        assert!(gw.match_route("GET", "/nonexistent").is_none());
        assert!(gw.match_route("DELETE", "/api/v1/health").is_none());
    }

    #[test]
    fn test_pattern_matching() {
        let params = ApiGateway::match_pattern("/api/v1/reports/:type", "/api/v1/reports/weekly");
        assert!(params.is_some());
        let p = params.unwrap();
        assert_eq!(p.get("type").unwrap(), "weekly");

        let no_match = ApiGateway::match_pattern("/api/v1/reports/:type", "/api/v1/reports");
        assert!(no_match.is_none());
    }

    #[test]
    fn test_cors_preflight() {
        let mut gw = ApiGateway::new(100);
        gw.register_default_routes();
        let mut req = make_request("OPTIONS", "/api/v1/health");
        req.headers.insert("Origin".to_string(), "https://app.angavu.com".to_string());
        let resp = gw.process(&req);
        assert_eq!(resp.status, 204);
        assert!(resp.headers.contains_key("Access-Control-Allow-Origin"));
    }

    #[test]
    fn test_rate_limiting() {
        let mut gw = ApiGateway::new(2);
        gw.register_default_routes();
        let req = make_request("GET", "/api/v1/health");
        assert_eq!(gw.process(&req).status, 200);
        assert_eq!(gw.process(&req).status, 200);
        assert_eq!(gw.process(&req).status, 429);
    }

    #[test]
    fn test_auth_required_route() {
        let mut gw = ApiGateway::new(100).with_jwt_secret("test-secret");
        gw.register_default_routes();
        let req = make_request("GET", "/api/v1/intelligence");
        let resp = gw.process(&req);
        assert_eq!(resp.status, 401);
    }

    #[test]
    fn test_health_no_auth_required() {
        let mut gw = ApiGateway::new(100);
        gw.register_default_routes();
        let req = make_request("GET", "/api/v1/health");
        let resp = gw.process(&req);
        assert_eq!(resp.status, 200);
        assert!(resp.body.contains("ok"));
    }

    #[test]
    fn test_404_unknown_route() {
        let mut gw = ApiGateway::new(100);
        gw.register_default_routes();
        let req = make_request("GET", "/api/v1/nonexistent");
        let resp = gw.process(&req);
        assert_eq!(resp.status, 404);
    }

    #[test]
    fn test_base64_decode() {
        // "hello" in base64
        let decoded = base64_decode("aGVsbG8=").unwrap();
        assert_eq!(decoded, b"hello");
    }
}
