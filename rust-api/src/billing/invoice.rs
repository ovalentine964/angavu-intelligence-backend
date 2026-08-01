// Invoice Generation — Create, store, and deliver billing invoices.
//
// Features:
// - Generate invoices for each billing cycle
// - Store in PostgreSQL `invoices` table
// - PDF generation using the `printpdf` crate
// - Email/WhatsApp delivery of invoices
//
// Invoice lifecycle:
//   Draft → Issued → Paid / Overdue / Void
//
// Each invoice includes:
// - Organization and subscription details
// - Line items (subscription fee, overage charges)
// - Payment status and M-Pesa receipt
// - Due date and payment terms

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ═══════════════════════════════════════════════════════════
//  TYPES
// ═══════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum InvoiceStatus {
    Draft,
    Issued,
    Paid,
    Overdue,
    Void,
}

impl InvoiceStatus {
    pub fn as_str(&self) -> &str {
        match self {
            Self::Draft => "draft",
            Self::Issued => "issued",
            Self::Paid => "paid",
            Self::Overdue => "overdue",
            Self::Void => "void",
        }
    }

    pub fn from_str(s: &str) -> Self {
        match s {
            "draft" => Self::Draft,
            "issued" => Self::Issued,
            "paid" => Self::Paid,
            "overdue" => Self::Overdue,
            "void" => Self::Void,
            _ => Self::Draft,
        }
    }
}

/// An invoice line item.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineItem {
    pub description: String,
    pub quantity: u32,
    pub unit_price_kes: f64,
    pub total_kes: f64,
}

/// Full invoice record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Invoice {
    pub id: String,
    pub invoice_number: String,        // human-readable: "INV-2026-00001"
    pub org_id: String,
    pub subscription_id: String,
    pub status: InvoiceStatus,
    pub currency: String,              // "KES"
    pub subtotal_kes: f64,
    pub tax_kes: f64,                  // 16% VAT
    pub total_kes: f64,
    pub line_items: Vec<LineItem>,
    pub description: String,
    pub mpesa_receipt: Option<String>,
    pub issued_at: DateTime<Utc>,
    pub due_date: DateTime<Utc>,
    pub paid_at: Option<DateTime<Utc>>,
    pub voided_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Query parameters for listing invoices.
#[derive(Debug, Deserialize)]
pub struct InvoiceListParams {
    pub status: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

// ═══════════════════════════════════════════════════════════
//  INVOICE CREATION
// ═══════════════════════════════════════════════════════════

/// Create a new invoice for a subscription billing cycle.
pub async fn create_invoice(
    db: &sqlx::PgPool,
    org_id: &str,
    subscription_id: &str,
    amount_kes: f64,
    description: &str,
) -> Result<Invoice, anyhow::Error> {
    let id = Uuid::new_v4().to_string();
    let now = Utc::now();
    let due_date = now + Duration::days(7); // 7 days to pay
    let invoice_number = generate_invoice_number(db).await?;

    // Calculate tax (16% VAT for Kenya)
    let subtotal = amount_kes;
    let tax = subtotal * 0.16;
    let total = subtotal + tax;

    let line_items = vec![LineItem {
        description: description.to_string(),
        quantity: 1,
        unit_price_kes: subtotal,
        total_kes: subtotal,
    }];

    let line_items_json = serde_json::to_value(&line_items)?;

    sqlx::query(
        r#"
        INSERT INTO invoices (
            id, invoice_number, org_id, subscription_id, status,
            currency, subtotal_kes, tax_kes, total_kes,
            line_items, description,
            issued_at, due_date, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, 'issued',
            'KES', $5, $6, $7,
            $8, $9,
            $10, $11, NOW(), NOW()
        )
        "#,
    )
    .bind(&id)
    .bind(&invoice_number)
    .bind(org_id)
    .bind(subscription_id)
    .bind(subtotal)
    .bind(tax)
    .bind(total)
    .bind(line_items_json)
    .bind(description)
    .bind(now)
    .bind(due_date)
    .execute(db)
    .await?;

    tracing::info!(
        invoice_id = %id,
        invoice_number = %invoice_number,
        org_id = %org_id,
        total = total,
        "Invoice created"
    );

    Ok(Invoice {
        id,
        invoice_number,
        org_id: org_id.to_string(),
        subscription_id: subscription_id.to_string(),
        status: InvoiceStatus::Issued,
        currency: "KES".to_string(),
        subtotal_kes: subtotal,
        tax_kes: tax,
        total_kes: total,
        line_items,
        description: description.to_string(),
        mpesa_receipt: None,
        issued_at: now,
        due_date,
        paid_at: None,
        voided_at: None,
        created_at: now,
        updated_at: now,
    })
}

// ═══════════════════════════════════════════════════════════
//  INVOICE QUERIES
// ═══════════════════════════════════════════════════════════

/// List invoices for an organization.
pub async fn list_invoices(
    db: &sqlx::PgPool,
    org_id: &str,
    params: InvoiceListParams,
) -> Result<Vec<Invoice>, anyhow::Error> {
    let limit = params.limit.unwrap_or(20).min(100);
    let offset = params.offset.unwrap_or(0);

    let rows = if let Some(ref status) = params.status {
        sqlx::query_as::<_, InvoiceRow>(
            r#"
            SELECT id, invoice_number, org_id, subscription_id, status,
                   currency, subtotal_kes, tax_kes, total_kes,
                   line_items, description, mpesa_receipt,
                   issued_at, due_date, paid_at, voided_at,
                   created_at, updated_at
            FROM invoices
            WHERE org_id = $1 AND status = $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
            "#,
        )
        .bind(org_id)
        .bind(status)
        .bind(limit)
        .bind(offset)
        .fetch_all(db)
        .await?
    } else {
        sqlx::query_as::<_, InvoiceRow>(
            r#"
            SELECT id, invoice_number, org_id, subscription_id, status,
                   currency, subtotal_kes, tax_kes, total_kes,
                   line_items, description, mpesa_receipt,
                   issued_at, due_date, paid_at, voided_at,
                   created_at, updated_at
            FROM invoices
            WHERE org_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            "#,
        )
        .bind(org_id)
        .bind(limit)
        .bind(offset)
        .fetch_all(db)
        .await?
    };

    Ok(rows.into_iter().map(|r| r.into_invoice()).collect())
}

/// Get a specific invoice by ID.
pub async fn get_invoice(
    db: &sqlx::PgPool,
    org_id: &str,
    invoice_id: &str,
) -> Result<Option<Invoice>, anyhow::Error> {
    let row = sqlx::query_as::<_, InvoiceRow>(
        r#"
        SELECT id, invoice_number, org_id, subscription_id, status,
               currency, subtotal_kes, tax_kes, total_kes,
               line_items, description, mpesa_receipt,
               issued_at, due_date, paid_at, voided_at,
               created_at, updated_at
        FROM invoices
        WHERE id = $1 AND org_id = $2
        "#,
    )
    .bind(invoice_id)
    .bind(org_id)
    .fetch_optional(db)
    .await?;

    Ok(row.map(|r| r.into_invoice()))
}

/// Mark an invoice as paid.
pub async fn mark_invoice_paid(
    db: &sqlx::PgPool,
    invoice_id: &str,
    mpesa_receipt: &str,
) -> Result<(), anyhow::Error> {
    let now = Utc::now();
    sqlx::query(
        r#"
        UPDATE invoices
        SET status = 'paid', mpesa_receipt = $1, paid_at = $2, updated_at = $2
        WHERE id = $3 AND status NOT IN ('paid', 'void')
        "#,
    )
    .bind(mpesa_receipt)
    .bind(now)
    .bind(invoice_id)
    .execute(db)
    .await?;

    Ok(())
}

// ═══════════════════════════════════════════════════════════
//  PDF GENERATION
// ═══════════════════════════════════════════════════════════

/// Generate a PDF for an invoice.
///
/// Returns the raw PDF bytes ready for download.
pub async fn generate_invoice_pdf(
    db: &sqlx::PgPool,
    org_id: &str,
    invoice_id: &str,
) -> Result<Vec<u8>, anyhow::Error> {
    let invoice = get_invoice(db, org_id, invoice_id).await?
        .ok_or_else(|| anyhow::anyhow!("Invoice not found"))?;

    generate_pdf_bytes(&invoice)
}

/// Generate PDF bytes from an Invoice struct.
///
/// Uses the `printpdf` crate for PDF generation.
fn generate_pdf_bytes(invoice: &Invoice) -> Result<Vec<u8>, anyhow::Error> {
    use printpdf::*;

    let (doc, page1, layer1) = PdfDocument::new(
        &format!("Invoice {}", invoice.invoice_number),
        Mm(210.0),  // A4 width
        Mm(297.0),  // A4 height
        "Layer 1",
    );

    let current_layer = doc.get_page(page1).get_layer(layer1);

    // Fonts
    let font = doc.add_builtin_font(BuiltinFont::Helvetica)?;
    let font_bold = doc.add_builtin_font(BuiltinFont::HelveticaBold)?;

    let mut y = 270.0f64; // Start from top

    // ── Header ──────────────────────────────────────────────
    current_layer.use_text("ANGAVU INTELLIGENCE", 24.0, Mm(20.0), Mm(y), &font_bold);
    y -= 10.0;
    current_layer.use_text("Revenue Intelligence Platform", 12.0, Mm(20.0), Mm(y), &font);
    y -= 15.0;

    // ── Invoice details ─────────────────────────────────────
    current_layer.use_text(
        &format!("Invoice: {}", invoice.invoice_number),
        14.0,
        Mm(20.0),
        Mm(y),
        &font_bold,
    );
    y -= 8.0;

    let details = vec![
        format!("Status: {:?}", invoice.status),
        format!("Issued: {}", invoice.issued_at.format("%d %B %Y")),
        format!("Due: {}", invoice.due_date.format("%d %B %Y")),
        format!("Currency: {}", invoice.currency),
        format!("Org ID: {}", invoice.org_id),
    ];

    for detail in details {
        current_layer.use_text(&detail, 10.0, Mm(20.0), Mm(y), &font);
        y -= 6.0;
    }

    y -= 5.0;

    // ── Line items table ────────────────────────────────────
    // Table header
    current_layer.use_text("Description", 10.0, Mm(20.0), Mm(y), &font_bold);
    current_layer.use_text("Qty", 10.0, Mm(120.0), Mm(y), &font_bold);
    current_layer.use_text("Unit Price", 10.0, Mm(140.0), Mm(y), &font_bold);
    current_layer.use_text("Total", 10.0, Mm(170.0), Mm(y), &font_bold);
    y -= 2.0;

    // Separator line
    current_layer.set_outline_color(Color::Rgb(Rgb::new(0.0, 0.0, 0.0, None)));
    current_layer.set_outline_thickness(0.5);
    current_layer.add_shape(Line {
        points: vec![
            (Point::new(Mm(20.0), Mm(y)), false),
            (Point::new(Mm(190.0), Mm(y)), false),
        ],
        is_closed: false,
    });
    y -= 6.0;

    // Line items
    for item in &invoice.line_items {
        current_layer.use_text(&item.description, 10.0, Mm(20.0), Mm(y), &font);
        current_layer.use_text(
            &item.quantity.to_string(),
            10.0,
            Mm(120.0),
            Mm(y),
            &font,
        );
        current_layer.use_text(
            &format!("KES {:.2}", item.unit_price_kes),
            10.0,
            Mm(140.0),
            Mm(y),
            &font,
        );
        current_layer.use_text(
            &format!("KES {:.2}", item.total_kes),
            10.0,
            Mm(170.0),
            Mm(y),
            &font,
        );
        y -= 6.0;
    }

    y -= 3.0;

    // Separator
    current_layer.add_shape(Line {
        points: vec![
            (Point::new(Mm(20.0), Mm(y)), false),
            (Point::new(Mm(190.0), Mm(y)), false),
        ],
        is_closed: false,
    });
    y -= 8.0;

    // ── Totals ──────────────────────────────────────────────
    current_layer.use_text("Subtotal:", 10.0, Mm(140.0), Mm(y), &font);
    current_layer.use_text(
        &format!("KES {:.2}", invoice.subtotal_kes),
        10.0,
        Mm(170.0),
        Mm(y),
        &font,
    );
    y -= 6.0;

    current_layer.use_text("VAT (16%):", 10.0, Mm(140.0), Mm(y), &font);
    current_layer.use_text(
        &format!("KES {:.2}", invoice.tax_kes),
        10.0,
        Mm(170.0),
        Mm(y),
        &font,
    );
    y -= 6.0;

    current_layer.use_text("TOTAL:", 12.0, Mm(140.0), Mm(y), &font_bold);
    current_layer.use_text(
        &format!("KES {:.2}", invoice.total_kes),
        12.0,
        Mm(170.0),
        Mm(y),
        &font_bold,
    );
    y -= 15.0;

    // ── Payment info ────────────────────────────────────────
    if let Some(ref receipt) = invoice.mpesa_receipt {
        current_layer.use_text(
            &format!("M-Pesa Receipt: {}", receipt),
            10.0,
            Mm(20.0),
            Mm(y),
            &font,
        );
        y -= 6.0;
    }

    if let Some(paid_at) = invoice.paid_at {
        current_layer.use_text(
            &format!("Paid on: {}", paid_at.format("%d %B %Y at %H:%M")),
            10.0,
            Mm(20.0),
            Mm(y),
            &font,
        );
        y -= 6.0;
    }

    y -= 10.0;

    // ── Payment instructions ────────────────────────────────
    current_layer.use_text("PAYMENT INSTRUCTIONS", 11.0, Mm(20.0), Mm(y), &font_bold);
    y -= 7.0;
    current_layer.use_text("Pay via M-Pesa:", 10.0, Mm(20.0), Mm(y), &font);
    y -= 6.0;
    current_layer.use_text("1. Go to Lipa na M-Pesa → Pay Bill", 10.0, Mm(25.0), Mm(y), &font);
    y -= 6.0;
    current_layer.use_text("2. Business No: 174379", 10.0, Mm(25.0), Mm(y), &font);
    y -= 6.0;
    current_layer.use_text(
        &format!("3. Account: {}", invoice.org_id),
        10.0,
        Mm(25.0),
        Mm(y),
        &font,
    );
    y -= 6.0;
    current_layer.use_text(
        &format!("4. Amount: KES {:.2}", invoice.total_kes),
        10.0,
        Mm(25.0),
        Mm(y),
        &font,
    );

    y -= 15.0;

    // ── Footer ──────────────────────────────────────────────
    current_layer.use_text(
        "Angavu Intelligence — Powering Africa's Informal Economy",
        9.0,
        Mm(20.0),
        Mm(y),
        &font,
    );
    y -= 5.0;
    current_layer.use_text(
        "support@angavu.co.ke | +254 700 000 000 | angavu.co.ke",
        9.0,
        Mm(20.0),
        Mm(y),
        &font,
    );

    // Serialize to bytes
    let mut buf = std::io::BufWriter::new(Vec::new());
    doc.save(&mut buf)?;
    let bytes = buf.into_inner()?;

    Ok(bytes)
}

// ═══════════════════════════════════════════════════════════
//  INVOICE NUMBER GENERATION
// ═══════════════════════════════════════════════════════════

/// Generate a human-readable invoice number: INV-YYYY-NNNNN
async fn generate_invoice_number(db: &sqlx::PgPool) -> Result<String, anyhow::Error> {
    let year = Utc::now().format("%Y").to_string();

    // Get the next sequence number for this year
    let count: (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM invoices WHERE invoice_number LIKE $1",
    )
    .bind(format!("INV-{}-%", year))
    .fetch_one(db)
    .await?;

    let seq = count.0 + 1;
    Ok(format!("INV-{}-{:05}", year, seq))
}

// ═══════════════════════════════════════════════════════════
//  DELIVERY (Email / WhatsApp)
// ═══════════════════════════════════════════════════════════

/// Send invoice via email.
/// This is a placeholder — integrate with an email service (SendGrid, AWS SES, etc.)
pub async fn send_invoice_email(
    db: &sqlx::PgPool,
    invoice_id: &str,
    recipient_email: &str,
) -> Result<(), anyhow::Error> {
    let pdf_bytes = generate_invoice_pdf(db, "", invoice_id).await?;

    // TODO: Integrate with email service
    // For now, log the attempt
    tracing::info!(
        invoice_id = %invoice_id,
        recipient = %recipient_email,
        pdf_size = pdf_bytes.len(),
        "Invoice email queued (email service integration pending)"
    );

    Ok(())
}

/// Send invoice via WhatsApp.
/// This is a placeholder — integrate with WhatsApp Business API.
pub async fn send_invoice_whatsapp(
    db: &sqlx::PgPool,
    invoice_id: &str,
    phone_number: &str,
) -> Result<(), anyhow::Error> {
    let pdf_bytes = generate_invoice_pdf(db, "", invoice_id).await?;

    // TODO: Integrate with WhatsApp Business API
    tracing::info!(
        invoice_id = %invoice_id,
        phone = %phone_number,
        pdf_size = pdf_bytes.len(),
        "Invoice WhatsApp delivery queued (WhatsApp API integration pending)"
    );

    Ok(())
}

// ═══════════════════════════════════════════════════════════
//  OVERDUE PROCESSING (called by background scheduler)
// ═══════════════════════════════════════════════════════════

/// Mark overdue invoices. Called daily by a cron job.
pub async fn process_overdue_invoices(db: &sqlx::PgPool) -> Result<u32, anyhow::Error> {
    let now = Utc::now();

    let result = sqlx::query(
        r#"
        UPDATE invoices
        SET status = 'overdue', updated_at = $1
        WHERE status = 'issued' AND due_date < $1
        "#,
    )
    .bind(now)
    .execute(db)
    .await?;

    let count = result.rows_affected() as u32;
    if count > 0 {
        tracing::info!(count = count, "Invoices marked as overdue");
    }

    Ok(count)
}

// ═══════════════════════════════════════════════════════════
//  DB ROW MAPPING
// ═══════════════════════════════════════════════════════════

#[derive(Debug, sqlx::FromRow)]
struct InvoiceRow {
    id: String,
    invoice_number: String,
    org_id: String,
    subscription_id: String,
    status: String,
    currency: String,
    subtotal_kes: f64,
    tax_kes: f64,
    total_kes: f64,
    line_items: serde_json::Value,
    description: String,
    mpesa_receipt: Option<String>,
    issued_at: DateTime<Utc>,
    due_date: DateTime<Utc>,
    paid_at: Option<DateTime<Utc>>,
    voided_at: Option<DateTime<Utc>>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl InvoiceRow {
    fn into_invoice(self) -> Invoice {
        Invoice {
            id: self.id,
            invoice_number: self.invoice_number,
            org_id: self.org_id,
            subscription_id: self.subscription_id,
            status: InvoiceStatus::from_str(&self.status),
            currency: self.currency,
            subtotal_kes: self.subtotal_kes,
            tax_kes: self.tax_kes,
            total_kes: self.total_kes,
            line_items: serde_json::from_value(self.line_items).unwrap_or_default(),
            description: self.description,
            mpesa_receipt: self.mpesa_receipt,
            issued_at: self.issued_at,
            due_date: self.due_date,
            paid_at: self.paid_at,
            voided_at: self.voided_at,
            created_at: self.created_at,
            updated_at: self.updated_at,
        }
    }
}

// ═══════════════════════════════════════════════════════════
//  MIGRATION SQL
// ═══════════════════════════════════════════════════════════

pub const INVOICE_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(64) PRIMARY KEY,
    invoice_number VARCHAR(32) UNIQUE NOT NULL,
    org_id VARCHAR(128) NOT NULL,
    subscription_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    currency VARCHAR(8) NOT NULL DEFAULT 'KES',
    subtotal_kes DOUBLE PRECISION NOT NULL DEFAULT 0,
    tax_kes DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_kes DOUBLE PRECISION NOT NULL DEFAULT 0,
    line_items JSONB NOT NULL DEFAULT '[]',
    description TEXT NOT NULL DEFAULT '',
    mpesa_receipt VARCHAR(64),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    due_date TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
    paid_at TIMESTAMPTZ,
    voided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_org ON invoices(org_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_due ON invoices(due_date) WHERE status = 'issued';
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);
"#;

// ═══════════════════════════════════════════════════════════
//  TESTS
// ═══════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_invoice_status_roundtrip() {
        let statuses = vec![
            InvoiceStatus::Draft,
            InvoiceStatus::Issued,
            InvoiceStatus::Paid,
            InvoiceStatus::Overdue,
            InvoiceStatus::Void,
        ];
        for s in statuses {
            assert_eq!(InvoiceStatus::from_str(s.as_str()), s);
        }
    }

    #[test]
    fn test_tax_calculation() {
        let subtotal = 500.0f64;
        let tax = subtotal * 0.16;
        let total = subtotal + tax;
        assert!((tax - 80.0).abs() < 0.01);
        assert!((total - 580.0).abs() < 0.01);
    }

    #[test]
    fn test_invoice_number_format() {
        // Should match INV-YYYY-NNNNN pattern
        let year = "2026";
        let seq = 42;
        let number = format!("INV-{}-{:05}", year, seq);
        assert_eq!(number, "INV-2026-00042");
    }
}
