import psycopg2
import json
import boto3
import os
import sys

def get_db_credentials():
    """Get database credentials from Secrets Manager."""
    secret_name = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
    region = os.getenv('AWS_REGION', 'us-east-1')
    client = boto3.client('secretsmanager', region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

def run_migration():
    """Run the database migration."""
    creds = get_db_credentials()

    conn = psycopg2.connect(
        host=creds['host'],
        database=creds['database'],
        user=creds['username'],
        password=creds['password'],
        port=creds['port']
    )
    conn.autocommit = True
    cur = conn.cursor()

    print("=" * 60)
    print("Starting database migration...")
    print("=" * 60)

    # --------------------------------------------------
    # Step 1: Ensure pgvector extension exists
    # --------------------------------------------------
    print("\n[1/7] Ensuring pgvector extension exists...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    print("  ✓ pgvector extension ready")

    # --------------------------------------------------
    # Step 2: Verify existing documents table
    # --------------------------------------------------
    print("\n[2/7] Checking existing documents table...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'documents'
        );
    """)
    documents_exists = cur.fetchone()[0]

    if documents_exists:
        cur.execute("SELECT COUNT(*) FROM documents;")
        doc_count = cur.fetchone()[0]
        print(f"  ✓ Documents table exists with {doc_count} records")
    else:
        print("  ⚠ Documents table not found, creating...")
        cur.execute("""
            CREATE TABLE documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                embedding vector(384),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("  ✓ Documents table created")

    # --------------------------------------------------
    # Step 3: Create ingested_records table
    # --------------------------------------------------
    print("\n[3/7] Creating ingested_records table...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'ingested_records'
        );
    """)
    table_exists = cur.fetchone()[0]

    if table_exists:
        print("  ⚠ Table already exists, skipping creation")
    else:
        cur.execute("""
            CREATE TABLE ingested_records (
                id SERIAL PRIMARY KEY,
                
                -- Source tracking
                source_file VARCHAR(255) NOT NULL,
                row_number INTEGER,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- Original data (store full row as JSONB for flexibility)
                raw_data JSONB NOT NULL,
                
                -- Searchable text fields (extracted from CSV)
                title TEXT,
                description TEXT,
                category VARCHAR(100),
                tags TEXT[],
                
                -- Combined searchable content (concatenation of key fields)
                searchable_content TEXT NOT NULL,
                
                -- Vector embeddings
                content_embedding vector(384),
                title_embedding vector(384),
                
                -- Metadata
                status VARCHAR(20) DEFAULT 'active',
                metadata JSONB DEFAULT '{}'
            );
        """)
        print("  ✓ ingested_records table created")

    # --------------------------------------------------
    # Step 4: Create ingestion_jobs table
    # --------------------------------------------------
    print("\n[4/7] Creating ingestion_jobs table...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'ingestion_jobs'
        );
    """)
    table_exists = cur.fetchone()[0]

    if table_exists:
        print("  ⚠ Table already exists, skipping creation")
    else:
        cur.execute("""
            CREATE TABLE ingestion_jobs (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(100) UNIQUE NOT NULL,
                source_file VARCHAR(255) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                total_rows INTEGER,
                processed_rows INTEGER DEFAULT 0,
                failed_rows INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("  ✓ ingestion_jobs table created")

    # --------------------------------------------------
    # Step 5: Create indexes for ingested_records
    # --------------------------------------------------
    print("\n[5/7] Creating vector indexes (HNSW)...")

    # Content embedding index
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE indexname = 'idx_records_content_embedding'
        );
    """)
    if not cur.fetchone()[0]:
        cur.execute("""
            CREATE INDEX idx_records_content_embedding 
            ON ingested_records 
            USING hnsw (content_embedding vector_cosine_ops);
        """)
        print("  ✓ Content embedding HNSW index created")
    else:
        print("  ⚠ Content embedding index already exists")

    # Title embedding index
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE indexname = 'idx_records_title_embedding'
        );
    """)
    if not cur.fetchone()[0]:
        cur.execute("""
            CREATE INDEX idx_records_title_embedding 
            ON ingested_records 
            USING hnsw (title_embedding vector_cosine_ops);
        """)
        print("  ✓ Title embedding HNSW index created")
    else:
        print("  ⚠ Title embedding index already exists")

    # --------------------------------------------------
    # Step 6: Create standard indexes
    # --------------------------------------------------
    print("\n[6/7] Creating standard indexes...")

    indexes = [
        ("idx_records_source_file", "CREATE INDEX idx_records_source_file ON ingested_records (source_file);"),
        ("idx_records_category", "CREATE INDEX idx_records_category ON ingested_records (category);"),
        ("idx_records_status", "CREATE INDEX idx_records_status ON ingested_records (status);"),
        ("idx_records_ingested_at", "CREATE INDEX idx_records_ingested_at ON ingested_records (ingested_at);"),
        ("idx_jobs_status", "CREATE INDEX idx_jobs_status ON ingestion_jobs (status);"),
        ("idx_jobs_created_at", "CREATE INDEX idx_jobs_created_at ON ingestion_jobs (created_at);"),
    ]

    for index_name, create_sql in indexes:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = %s
            );
        """, (index_name,))

        if not cur.fetchone()[0]:
            cur.execute(create_sql)
            print(f"  ✓ {index_name} created")
        else:
            print(f"  ⚠ {index_name} already exists")

    # --------------------------------------------------
    # Step 7: Verify migration
    # --------------------------------------------------
    print("\n[7/7] Verifying migration...")

    # Check all tables exist
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"  Tables: {', '.join(tables)}")

    # Check all indexes
    cur.execute("""
        SELECT indexname, tablename
        FROM pg_indexes 
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname;
    """)
    print("  Indexes:")
    for row in cur.fetchall():
        print(f"    - {row[0]} (on {row[1]})")

    # Check pgvector version
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
    pgvector_version = cur.fetchone()
    if pgvector_version:
        print(f"  pgvector version: {pgvector_version[0]}")

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)

    cur.close()
    conn.close()

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)