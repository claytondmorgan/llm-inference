import psycopg2
import json
import boto3
import os

def get_db_credentials():
    secret_name = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
    region = os.getenv('AWS_REGION', 'us-east-1')
    client = boto3.client('secretsmanager', region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

def fix_index():
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

    print("Dropping old IVFFlat index...")
    cur.execute("DROP INDEX IF EXISTS documents_embedding_idx;")

    print("Creating HNSW index (works with any number of documents)...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS documents_embedding_idx
        ON documents
        USING hnsw (embedding vector_cosine_ops);
    """)

    print("Index fix complete!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    fix_index()
