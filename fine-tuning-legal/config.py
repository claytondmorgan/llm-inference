import os
import json

# Database - AWS Secrets Manager (same as app.py)
DB_SECRET_NAME = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Embedding model (768-dim, fine-tuned on US legal opinions)
BASE_MODEL = "freelawproject/modernbert-embed-base_finetune_512"
FINETUNED_MODEL_DIR = os.path.join(os.path.dirname(__file__), "fine-tuned-modernbert-legal")
EMBEDDING_DIM = 768

# Which embedding field to fine-tune on (content is the primary search corpus)
# The same model generates title, content, and headnote embeddings, so improving
# the model's legal text understanding improves all three.
FINE_TUNE_ON = "content"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Data generation mode
USE_CLAUDE = False

# Training (adjusted for smaller 58-doc corpus)
TRAIN_EPOCHS = 5          # More epochs for smaller dataset
BATCH_SIZE = 16            # Smaller batch since fewer training pairs
LEARNING_RATE = 2e-5
WARMUP_RATIO = 0.1
QUERIES_PER_DOCUMENT = 10  # 10 queries x 58 docs = ~580 pairs

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "legal-documents.csv")

# ALB URL for live API testing
ALB_URL = os.getenv("ALB_URL", "http://llm-alb-1402483560.us-east-1.elb.amazonaws.com")


def get_db_credentials():
    """Get database credentials from AWS Secrets Manager (same as app.py)."""
    import boto3
    client = boto3.client('secretsmanager', region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=DB_SECRET_NAME)
    return json.loads(response['SecretString'])


def get_db_connection():
    """Create a database connection."""
    import psycopg2
    creds = get_db_credentials()
    return psycopg2.connect(
        host=creds['host'],
        database=creds['database'],
        user=creds['username'],
        password=creds['password'],
        port=creds['port']
    )