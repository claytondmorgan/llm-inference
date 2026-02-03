import os

# Database (your existing RDS PostgreSQL)
DB_HOST = os.getenv("DB_HOST", "llm-postgres.cgd6mmmueuhm.us-east-1.rds.amazonaws.com")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "llmdb")
DB_USER = os.getenv("DB_USERNAME", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "")

# Embedding model
BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FINETUNED_MODEL_DIR = os.path.join(os.path.dirname(__file__), "fine-tuned-all-MiniLM-L6-v2-amazon")
EMBEDDING_DIM = 384

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Data generation mode
# Set to True to use Claude API for high-quality query generation
# Set to False for rule-based programmatic generation (faster, no API cost)
USE_CLAUDE = False

# Training
TRAIN_EPOCHS = 3
BATCH_SIZE = 32
LEARNING_RATE = 2e-5
WARMUP_RATIO = 0.1
QUERIES_PER_PRODUCT = 4

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TRAINING_DATA_PATH = os.path.join(DATA_DIR, "training_pairs.json")
TRAIN_SPLIT_PATH = os.path.join(DATA_DIR, "train_split.json")
TEST_SPLIT_PATH = os.path.join(DATA_DIR, "test_split.json")
PRODUCTS_PATH = os.path.join(DATA_DIR, "products.json")
BASELINE_RESULTS_PATH = os.path.join(DATA_DIR, "baseline_results.json")
FINETUNED_RESULTS_PATH = os.path.join(DATA_DIR, "finetuned_results.json")

