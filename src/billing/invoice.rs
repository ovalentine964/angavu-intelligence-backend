//! Invoice generation for Angavu Intelligence billing.
//!
//! Produces invoices from subscription data and usage records,
//! calculates line items with overage charges, and stores them
//! for retrieval and payment processing.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use thiserror::Error;

use super::subscription::{Subscription, SubscriptionTier};
use super::usage::{UsageMetric, UsageRecord};

// ── Errors ─────────────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum InvoiceError {
    #[error("invoice not found: {0}")]
    NotFound(Uuid),
    #[error("invoice already exists for subscription {sub_id} period {period_start}")]
    AlreadyExists {
        sub_id: Uuid,
        period_start: String,
    },
    #[error("invoice is not in draft status")]
    NotDraft,
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
}

// ── Invoice Status ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InvoiceStatus {
    Draft,
    Finalized,
    Paid,
    Void,
    Overdue,
}

impl InvoiceStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Draft => "draft",
            Self::Finalized => "finalized",
            Self::Paid => "paid",
            Self::Void => "void",
            Self::Overdue => "overdue",
        }
    }
}

// ── Invoice Line Item ──────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvoiceLineItem {
    pub description: String,
    pub metric: String,
    pub quantity: u64,
    pub unit_price_cents: u64,
    pub total_cents: u64,
}

// ── Invoice Model ──────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Invoice {
    pub id: Uuid,
    pub org_id: Uuid,
    pub subscription_id: Uuid,
    pub invoice_number: String,
    pub status: String,
    pub currency: String,
    pub subtotal_cents: i64,
    pub tax_cents: i64,
    pub total_cents: i64,
    pub period_start: DateTime<Utc>,
    pub period_end: DateTime<Utc>,
    pub due_date: DateTime<Utc>,
    pub paid_at: Option<DateTime<Utc>>,
    pub line_items: serde_json::Value,
    pub notes: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Invoice {
    /// Parse the stored status string.
    pub fn status_enum(&self) -> InvoiceStatus {
        match self.status.as_str() {
            "draft" => InvoiceStatus::Draft,
            "finalized" => InvoiceStatus::Finalized,
            "paid" => InvoiceStatus::Paid,
            "void" => InvoiceStatus::Void,
            "overdue" => InvoiceStatus::Overdue,
            _ => InvoiceStatus::Draft,
        }
    }

    /// Deserialize line items from JSON.
    pub fn parsed_line_items(&self) -> Vec<InvoiceLineItem> {
        serde_json::from_value(self.line_items.clone()).unwrap_or_default()
    }
}

// ── Invoice Generator ──────────────────────────────────────────────────

pub struct InvoiceGenerator {
    pool: PgPool,
}

impl InvoiceGenerator {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// Generate an invoice for a subscription's billing period from usage records.
    pub async fn generate(
        &self,
        subscription: &Subscription,
        usage_records: &[UsageRecord],
    ) -> Result<Invoice, InvoiceError> {
        let tier = subscription.tier_enum();

        // Check for existing invoice for this period
        let existing = sqlx::query_as::<_, Invoice>(
            r#"
            SELECT * FROM invoices
            WHERE subscription_id = $1
              AND period_start = $2
              AND status != 'void'
            "#,
        )
        .bind(subscription.id)
        .bind(subscription.current_period_start)
        .fetch_optional(&self.pool)
        .await?;

        if existing.is_some() {
            return Err(InvoiceError::AlreadyExists {
                sub_id: subscription.id,
                period_start: subscription.current_period_start.to_rfc3339(),
            });
        }

        // Build line items
        let mut line_items: Vec<InvoiceLineItem> = Vec::new();

        // 1. Base subscription fee
        if let Some(base_price) = tier.monthly_price_cents() {
            if base_price > 0 {
                line_items.push(InvoiceLineItem {
                    description: format!("Angavu Intelligence — {} Plan (monthly)", tier),
                    metric: "subscription".to_string(),
                    quantity: 1,
                    unit_price_cents: base_price,
                    total_cents: base_price,
                });
            }
        }

        // 2. Overage charges from usage records
        let overage_items = self.calculate_overage(subscription, usage_records);
        line_items.extend(overage_items);

        // 3. Custom pricing for enterprise
        if let Some(custom_price) = subscription.custom_price_cents {
            line_items.push(InvoiceLineItem {
                description: "Enterprise custom pricing".to_string(),
                metric: "enterprise_custom".to_string(),
                quantity: 1,
                unit_price_cents: custom_price,
                total_cents: custom_price,
            });
        }

        let subtotal: u64 = line_items.iter().map(|li| li.total_cents).sum();

        // Tax: 16% VAT for Kenya (configurable in production)
        let tax_rate = 0.16f64;
        let tax = (subtotal as f64 * tax_rate).round() as u64;
        let total = subtotal + tax;

        let now = Utc::now();
        let invoice_number = self.generate_invoice_number().await?;
        let due_date = now + chrono::Duration::days(30);

        let invoice = sqlx::query_as::<_, Invoice>(
            r#"
            INSERT INTO invoices (id, org_id, subscription_id, invoice_number, status,
                                  currency, subtotal_cents, tax_cents, total_cents,
                                  period_start, period_end, due_date, paid_at,
                                  line_items, notes, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'draft', 'USD', $5, $6, $7, $8, $9, $10, NULL, $11, NULL, $12, $12)
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(subscription.org_id)
        .bind(subscription.id)
        .bind(&invoice_number)
        .bind(subtotal as i64)
        .bind(tax as i64)
        .bind(total as i64)
        .bind(subscription.current_period_start)
        .bind(subscription.current_period_end)
        .bind(due_date)
        .bind(serde_json::to_value(&line_items).unwrap_or_default())
        .bind(now)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            invoice_id = %invoice.id,
            invoice_number = %invoice_number,
            org_id = %subscription.org_id,
            total_cents = total,
            "Invoice generated"
        );

        Ok(invoice)
    }

    /// Calculate overage line items from usage records.
    fn calculate_overage(
        &self,
        subscription: &Subscription,
        usage_records: &[UsageRecord],
    ) -> Vec<InvoiceLineItem> {
        use std::collections::HashMap;

        let tier = subscription.tier_enum();

        // Aggregate usage by metric
        let mut metric_totals: HashMap<String, i64> = HashMap::new();
        let mut metric_costs: HashMap<String, i64> = HashMap::new();

        for record in usage_records {
            *metric_totals.entry(record.metric.clone()).or_insert(0) += record.quantity;
            *metric_costs.entry(record.metric.clone()).or_insert(0) += record.total_cost_cents;
        }

        let mut items = Vec::new();

        // Only add overage items if there are actual costs beyond the base subscription
        for (metric, total_cost) in &metric_costs {
            if *total_cost > 0 {
                let quantity = metric_totals.get(metric).copied().unwrap_or(0) as u64;
                items.push(InvoiceLineItem {
                    description: format!("Overage: {} ({} units)", metric, quantity),
                    metric: metric.clone(),
                    quantity,
                    unit_price_cents: if quantity > 0 {
                        (*total_cost as u64) / quantity
                    } else {
                        0
                    },
                    total_cents: *total_cost as u64,
                });
            }
        }

        items
    }

    /// Generate a sequential invoice number: `ANG-2026-000001`
    async fn generate_invoice_number(&self) -> Result<String, InvoiceError> {
        let year = Utc::now().format("%Y");

        // Use a Postgres sequence for atomicity
        let seq_val: (i64,) = sqlx::query_as(
            "SELECT nextval('invoice_number_seq')",
        )
        .fetch_one(&self.pool)
        .await?;

        Ok(format!("ANG-{}-{:06}", year, seq_val.0))
    }

    /// Finalize a draft invoice (makes it payable).
    pub async fn finalize(&self, invoice_id: Uuid) -> Result<Invoice, InvoiceError> {
        let invoice = self.get_by_id(invoice_id).await?;
        if invoice.status_enum() != InvoiceStatus::Draft {
            return Err(InvoiceError::NotDraft);
        }

        let now = Utc::now();
        let updated = sqlx::query_as::<_, Invoice>(
            r#"
            UPDATE invoices
            SET status = 'finalized', updated_at = $1
            WHERE id = $2
            RETURNING *
            "#,
        )
        .bind(now)
        .bind(invoice_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(invoice_id = %invoice_id, "Invoice finalized");
        Ok(updated)
    }

    /// Mark an invoice as paid.
    pub async fn mark_paid(&self, invoice_id: Uuid) -> Result<Invoice, InvoiceError> {
        let now = Utc::now();
        let updated = sqlx::query_as::<_, Invoice>(
            r#"
            UPDATE invoices
            SET status = 'paid', paid_at = $1, updated_at = $1
            WHERE id = $2
            RETURNING *
            "#,
        )
        .bind(now)
        .bind(invoice_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(invoice_id = %invoice_id, "Invoice marked as paid");
        Ok(updated)
    }

    /// Void an invoice.
    pub async fn void_invoice(&self, invoice_id: Uuid) -> Result<Invoice, InvoiceError> {
        let now = Utc::now();
        let updated = sqlx::query_as::<_, Invoice>(
            r#"
            UPDATE invoices
            SET status = 'void', updated_at = $1
            WHERE id = $2
            RETURNING *
            "#,
        )
        .bind(now)
        .bind(invoice_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(invoice_id = %invoice_id, "Invoice voided");
        Ok(updated)
    }

    /// Get an invoice by ID.
    pub async fn get_by_id(&self, id: Uuid) -> Result<Invoice, InvoiceError> {
        let invoice = sqlx::query_as::<_, Invoice>(
            "SELECT * FROM invoices WHERE id = $1",
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await?
        .ok_or(InvoiceError::NotFound(id))?;
        Ok(invoice)
    }

    /// List all invoices for an org.
    pub async fn list_for_org(&self, org_id: Uuid) -> Result<Vec<Invoice>, InvoiceError> {
        let invoices = sqlx::query_as::<_, Invoice>(
            "SELECT * FROM invoices WHERE org_id = $1 ORDER BY created_at DESC",
        )
        .bind(org_id)
        .fetch_all(&self.pool)
        .await?;
        Ok(invoices)
    }

    /// List overdue invoices (past due date, not paid).
    pub async fn list_overdue(&self) -> Result<Vec<Invoice>, InvoiceError> {
        let now = Utc::now();
        let invoices = sqlx::query_as::<_, Invoice>(
            r#"
            SELECT * FROM invoices
            WHERE status = 'finalized' AND due_date < $1
            ORDER BY due_date
            "#,
        )
        .bind(now)
        .fetch_all(&self.pool)
        .await?;

        // Mark them overdue
        for inv in &invoices {
            let _ = sqlx::query(
                "UPDATE invoices SET status = 'overdue', updated_at = $1 WHERE id = $2",
            )
            .bind(now)
            .bind(inv.id)
            .execute(&self.pool)
            .await;
        }

        Ok(invoices)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invoice_status_display() {
        assert_eq!(InvoiceStatus::Draft.as_str(), "draft");
        assert_eq!(InvoiceStatus::Paid.as_str(), "paid");
    }

    #[test]
    fn line_item_serialization() {
        let item = InvoiceLineItem {
            description: "Test".to_string(),
            metric: "query".to_string(),
            quantity: 100,
            unit_price_cents: 2,
            total_cents: 200,
        };
        let json = serde_json::to_value(&item).unwrap();
        assert_eq!(json["quantity"], 100);
        assert_eq!(json["total_cents"], 200);
    }
}
