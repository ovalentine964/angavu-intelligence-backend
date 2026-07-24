use chrono::{DateTime, Duration, Utc};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use anyhow::Result;
use crate::models::{Claims, UserRole};

pub struct JwtService {
    encoding_key: EncodingKey,
    decoding_key: DecodingKey,
    expiration: i64,
}

impl JwtService {
    pub fn new(secret: &str, expiration: u64) -> Self {
        Self {
            encoding_key: EncodingKey::from_secret(secret.as_bytes()),
            decoding_key: DecodingKey::from_secret(secret.as_bytes()),
            expiration: expiration as i64,
        }
    }

    pub fn generate_token(&self, user_id: Uuid, email: &str, role: UserRole, org_id: Uuid) -> Result<(String, DateTime<Utc>)> {
        let now = Utc::now();
        let expires_at = now + Duration::seconds(self.expiration);

        let claims = Claims {
            sub: user_id,
            email: email.to_string(),
            role,
            org_id,
            exp: expires_at.timestamp() as usize,
            iat: now.timestamp() as usize,
        };

        let token = encode(&Header::default(), &claims, &self.encoding_key)?;
        Ok((token, expires_at))
    }

    pub fn validate_token(&self, token: &str) -> Result<Claims> {
        let token_data = decode::<Claims>(token, &self.decoding_key, &Validation::default())?;
        Ok(token_data.claims)
    }

    pub fn refresh_token(&self, token: &str) -> Result<(String, DateTime<Utc>)> {
        let claims = self.validate_token(token)?;
        self.generate_token(claims.sub, &claims.email, claims.role, claims.org_id)
    }
}

/// API Key authentication
pub struct ApiKeyService {
    keys: dashmap::DashMap<String, ApiKeyInfo>,
}

#[derive(Debug, Clone)]
pub struct ApiKeyInfo {
    pub key_id: String,
    pub user_id: Uuid,
    pub org_id: Uuid,
    pub permissions: Vec<String>,
    pub rate_limit: u32,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
}

impl ApiKeyService {
    pub fn new() -> Self {
        Self {
            keys: dashmap::DashMap::new(),
        }
    }

    pub fn create_key(&self, user_id: Uuid, org_id: Uuid, permissions: Vec<String>, rate_limit: u32) -> (String, String) {
        let key_id = Uuid::new_v4().to_string();
        let api_key = crate::security::SecureRandom::generate_api_key();
        
        let info = ApiKeyInfo {
            key_id: key_id.clone(),
            user_id,
            org_id,
            permissions,
            rate_limit,
            created_at: Utc::now(),
            expires_at: None,
        };
        
        self.keys.insert(api_key.clone(), info);
        (key_id, api_key)
    }

    pub fn validate_key(&self, api_key: &str) -> Option<ApiKeyInfo> {
        self.keys.get(api_key).map(|entry| entry.value().clone())
    }

    pub fn revoke_key(&self, api_key: &str) -> bool {
        self.keys.remove(api_key).is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jwt_token() {
        let service = JwtService::new("test-secret", 3600);
        let user_id = Uuid::new_v4();
        let org_id = Uuid::new_v4();
        
        let (token, _) = service.generate_token(
            user_id,
            "test@example.com",
            UserRole::Analyst,
            org_id,
        ).unwrap();
        
        let claims = service.validate_token(&token).unwrap();
        assert_eq!(claims.sub, user_id);
        assert_eq!(claims.email, "test@example.com");
    }

    #[test]
    fn test_api_key() {
        let service = ApiKeyService::new();
        let user_id = Uuid::new_v4();
        let org_id = Uuid::new_v4();
        
        let (key_id, api_key) = service.create_key(
            user_id,
            org_id,
            vec!["read".to_string(), "write".to_string()],
            1000,
        );
        
        let info = service.validate_key(&api_key).unwrap();
        assert_eq!(info.user_id, user_id);
        
        assert!(service.revoke_key(&api_key));
        assert!(service.validate_key(&api_key).is_none());
    }
}
