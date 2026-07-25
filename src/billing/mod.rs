//! # Billing Module
//!
//! Provides subscription management, API key authentication, usage metering,
//! and invoice generation for the Angavu Intelligence platform.
//!
//! ## Pricing Tiers (from revenue model research)
//!
//! | Tier         | Monthly Price | Queries/mo | Reports/mo | Data Exports/mo |
//! |-------------|---------------|-----------|------------|----------------|
//! | Free        | $0            | 100       | 2          | 0              |
//! | Starter     | $299          | 5,000     | 20         | 5              |
//! | Pro         | $1,499        | 50,000    | 100        | 50             |
//! | Enterprise  | Custom        | Unlimited | Unlimited  | Unlimited      |

pub mod api_keys;
pub mod invoice;
pub mod middleware;
pub mod subscription;
pub mod usage;

pub use api_keys::{ApiKey, ApiKeyManager, ApiKeyScope};
pub use invoice::{Invoice, InvoiceLineItem, InvoiceStatus, InvoiceGenerator};
pub use middleware::AuthenticatedBilling;
pub use subscription::{Subscription, SubscriptionTier, SubscriptionManager, SubscriptionStatus};
pub use usage::{UsageRecord, UsageMeter, UsageMetric};
