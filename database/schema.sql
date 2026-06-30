-- Msaidizi Database Schema (PostgreSQL)

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    assistant_name VARCHAR(100),
    business_description TEXT,
    business_location VARCHAR(200),
    business_hours VARCHAR(100),
    language VARCHAR(10) DEFAULT 'sw',
    report_time VARCHAR(20) DEFAULT 'evening',
    speed VARCHAR(10) DEFAULT 'normal',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS whatsapp_connections (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL,
    connected BOOLEAN DEFAULT FALSE,
    connected_at TIMESTAMP,
    assistant_name VARCHAR(100),
    language VARCHAR(10) DEFAULT 'sw',
    report_time VARCHAR(20) DEFAULT 'evening',
    reports_enabled BOOLEAN DEFAULT TRUE,
    last_report_sent TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS verifications (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    user_name VARCHAR(100),
    assistant_name VARCHAR(100),
    language VARCHAR(10) DEFAULT 'sw',
    report_time VARCHAR(20) DEFAULT 'evening',
    code VARCHAR(10),
    status VARCHAR(20) DEFAULT 'pending',
    whatsapp_id VARCHAR(100),
    delivery_receipt_received BOOLEAN DEFAULT FALSE,
    attempts INT DEFAULT 0,
    last_attempt_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    connected_at TIMESTAMP,
    expired_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    type VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    description TEXT,
    product_name VARCHAR(200),
    quantity INT DEFAULT 1,
    payment_method VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10, 2),
    cost DECIMAL(10, 2),
    stock INT DEFAULT 0,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    date DATE NOT NULL,
    total_sales DECIMAL(10, 2) DEFAULT 0,
    total_expenses DECIMAL(10, 2) DEFAULT 0,
    total_profit DECIMAL(10, 2) DEFAULT 0,
    items_sold INT DEFAULT 0,
    top_product VARCHAR(200),
    top_product_sales DECIMAL(10, 2),
    transaction_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS weekly_summaries (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    total_sales DECIMAL(10, 2) DEFAULT 0,
    total_expenses DECIMAL(10, 2) DEFAULT 0,
    total_profit DECIMAL(10, 2) DEFAULT 0,
    items_sold INT DEFAULT 0,
    best_day DATE,
    best_day_sales DECIMAL(10, 2),
    worst_day DATE,
    worst_day_sales DECIMAL(10, 2),
    transaction_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, week_start),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    content TEXT,
    openwa_message_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'sent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_whatsapp_connections_user_id ON whatsapp_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_connections_phone ON whatsapp_connections(phone);
CREATE INDEX IF NOT EXISTS idx_verifications_user_id ON verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_products_user_id ON products(user_id);
CREATE INDEX IF NOT EXISTS idx_daily_summaries_user_date ON daily_summaries(user_id, date);
CREATE INDEX IF NOT EXISTS idx_weekly_summaries_user_week ON weekly_summaries(user_id, week_start);
