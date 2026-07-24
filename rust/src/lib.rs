use pyo3::prelude::*;

mod crypto;
mod transaction;
mod sync;
mod validation;
mod vector;

/// Angavu Intelligence — Rust performance layer
///
/// Exposes high-performance crypto, transaction processing, sync,
/// validation, and vector operations to Python via PyO3.
#[pymodule]
fn angavu_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // ── Crypto ───────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(crypto::aes::encrypt_aes_gcm, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::aes::decrypt_aes_gcm, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::key_mgmt::generate_key, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::key_mgmt::generate_key_pair_hex, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::hashing::sha256_hash, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::hashing::sha256_hash_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::hashing::argon2_hash, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::hashing::argon2_verify, m)?)?;

    // ── Transaction ──────────────────────────────────────────
    m.add_function(wrap_pyfunction!(transaction::processor::process_transactions_batch, m)?)?;
    m.add_function(wrap_pyfunction!(transaction::validator::validate_transaction, m)?)?;
    m.add_function(wrap_pyfunction!(transaction::parser::parse_mpesa_sms, m)?)?;
    m.add_function(wrap_pyfunction!(transaction::parser::parse_mpesa_sms_batch, m)?)?;

    // ── Sync ─────────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(sync::conflict::resolve_conflicts, m)?)?;
    m.add_function(wrap_pyfunction!(sync::delta::compute_delta, m)?)?;
    m.add_function(wrap_pyfunction!(sync::delta::apply_delta, m)?)?;

    // ── Validation ───────────────────────────────────────────
    m.add_function(wrap_pyfunction!(validation::sanitize::sanitize_input, m)?)?;
    m.add_function(wrap_pyfunction!(validation::sanitize::sanitize_input_batch, m)?)?;
    m.add_function(wrap_pyfunction!(validation::phone::validate_phone_ke, m)?)?;
    m.add_function(wrap_pyfunction!(validation::phone::normalize_phone_ke, m)?)?;

    // ── Vector ───────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(vector::cosine::cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(vector::cosine::cosine_similarity_batch, m)?)?;
    m.add_function(wrap_pyfunction!(vector::batch::batch_dot_product, m)?)?;
    m.add_function(wrap_pyfunction!(vector::batch::batch_normalize, m)?)?;

    Ok(())
}
