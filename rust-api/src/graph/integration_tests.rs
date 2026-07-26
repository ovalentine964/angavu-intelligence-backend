// rust-api/src/graph/integration_tests.rs

#[cfg(test)]
mod integration_tests {
    use sqlx::PgPool;

    #[sqlx::test]
    async fn test_knowledge_graph_cohort_insert(pool: PgPool) -> sqlx::Result<()> {
        // Insert a worker cohort
        let cohort_id = sqlx::query_scalar!(
            "INSERT INTO kg_worker_cohorts (
                cohort_hash, worker_type, region_id, language_primary,
                scale_bucket, member_count, avg_daily_revenue
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id",
            "test_hash_123",
            "mama_mboga",
            "nairobi-eastlands",
            "sw",
            "micro",
            50,  // k=50, well above k≥10
            15000.0
        )
        .fetch_one(&pool)
        .await?;

        // Verify it exists
        let row = sqlx::query!(
            "SELECT member_count FROM kg_worker_cohorts WHERE id = $1",
            cohort_id
        )
        .fetch_one(&pool)
        .await?;

        assert_eq!(row.member_count, 50);
        Ok(())
    }

    #[sqlx::test]
    async fn test_k_anonymity_enforcement(pool: PgPool) -> sqlx::Result<()> {
        // Try to insert a cohort with k < 10 — should fail
        let result = sqlx::query!(
            "INSERT INTO kg_worker_cohorts (
                cohort_hash, worker_type, region_id, language_primary,
                scale_bucket, member_count
            ) VALUES ($1, $2, $3, $4, $5, $6)",
            "small_cohort",
            "mama_mboga",
            "nairobi-eastlands",
            "sw",
            "solo",
            5,  // k=5, below k≥10
        )
        .execute(&pool)
        .await;

        // Should fail due to CHECK constraint
        assert!(result.is_err());
        Ok(())
    }

    #[sqlx::test]
    async fn test_knowledge_graph_edge_traversal(pool: PgPool) -> sqlx::Result<()> {
        // Insert cohort and product
        let cohort_id = sqlx::query_scalar!(
            "INSERT INTO kg_worker_cohorts (
                cohort_hash, worker_type, region_id, language_primary,
                scale_bucket, member_count
            ) VALUES ('traversal_test', 'mama_mboga', 'nairobi', 'sw', 'micro', 50)
            RETURNING id"
        )
        .fetch_one(&pool)
        .await?;

        let product_id = sqlx::query_scalar!(
            "INSERT INTO kg_product_categories (category_code, category_name)
            VALUES ('vegetables', 'Vegetables')
            ON CONFLICT (category_code) DO UPDATE SET category_name = EXCLUDED.category_name
            RETURNING id"
        )
        .fetch_one(&pool)
        .await?;

        // Create edge
        sqlx::query!(
            "INSERT INTO kg_edges (
                source_type, source_id, target_type, target_id,
                edge_type, weight, sample_size
            ) VALUES ('worker_cohort', $1, 'product_category', $2,
                      'generates_signal', 0.8, 50)",
            cohort_id,
            product_id,
        )
        .execute(&pool)
        .await?;

        // Traverse: find products for this cohort
        let products = sqlx::query!(
            "SELECT pc.category_code, pc.category_name, e.weight
             FROM kg_edges e
             JOIN kg_product_categories pc ON pc.id = e.target_id
             WHERE e.source_id = $1 AND e.source_type = 'worker_cohort'",
            cohort_id
        )
        .fetch_all(&pool)
        .await?;

        assert_eq!(products.len(), 1);
        assert_eq!(products[0].category_code, "vegetables");
        Ok(())
    }
}
