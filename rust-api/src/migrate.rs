// Angavu Intelligence Backend — Database Migration Runner
// Runs SQL migrations from the migrations/ directory

use sqlx::postgres::PgPoolOptions;
use std::path::Path;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let database_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgresql://angavu:angavu_secret@localhost:5432/angavu".to_string());

    println!("Connecting to database...");
    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await?;

    println!("Running migrations...");

    let migrations_dir = Path::new("migrations");
    let mut entries: Vec<_> = std::fs::read_dir(migrations_dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map_or(false, |ext| ext == "sql"))
        .collect();

    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let path = entry.path();
        let name = path.file_name().unwrap().to_string_lossy();
        let sql = std::fs::read_to_string(&path)?;

        println!("  Applying: {}", name);
        sqlx::raw_sql(&sql).execute(&pool).await?;
        println!("  ✓ {}", name);
    }

    println!("All migrations applied successfully.");
    Ok(())
}
