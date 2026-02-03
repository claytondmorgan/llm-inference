import psycopg2
import os
import json
import boto3

def get_db_credentials():
    """Get credentials from environment or Secrets Manager."""
    secret_name = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    client = boto3.client('secretsmanager', region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

def setup_database():
    """Initialize pgvector and create tables."""
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
    
    print("Enabling pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    print("Creating documents table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            embedding vector(384),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    print("Creating vector index...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS documents_embedding_idx 
        ON documents 
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)
    
    print("Database setup complete!")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    setup_database()
