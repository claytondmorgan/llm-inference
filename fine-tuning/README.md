# Embedding Model Fine-Tuning

Fine-tune the `all-MiniLM-L6-v2` sentence transformer model for improved Amazon product search relevancy.

## Quick Start

The easiest way to run the fine-tuning process is with the interactive demo:

```bash
# 1. Install dependencies
cd fine-tuning
pip install -r requirements.txt

# 2. Set environment variables (macOS requires KMP_DUPLICATE_LIB_OK)
export KMP_DUPLICATE_LIB_OK=TRUE

# 3. Run the interactive demo
python demo.py
```

The demo will guide you through each step:
1. **Extract Products** - Load product data from CSV
2. **Generate Training Data** - Create synthetic search queries
3. **Baseline Evaluation** - Measure model performance before fine-tuning
4. **Fine-Tune Model** - Train the embedding model (~2-3 min on CPU)
5. **Evaluate Improvement** - Compare baseline vs fine-tuned metrics
6. **Generate Report** - Create a detailed evaluation report

At each step, the demo explains what's happening and shows results before continuing.

---

## Prerequisites

- Python 3.9+
- pip
- Anthropic API key (for synthetic data generation)
- PostgreSQL database with product data

## Installation

```bash
cd fine-tuning
pip install -r requirements.txt
```

### Verify Installation

```bash
python -c "from sentence_transformers import SentenceTransformer; print('OK')"
```

## Scripts

Run in order:

| Script | Description |
|--------|-------------|
| `01_extract_products.py` | Extract products from PostgreSQL |
| `02_generate_training_data.py` | Generate synthetic queries with Claude |
| `03_baseline_evaluation.py` | Evaluate base model (before fine-tuning) |
| `04_fine_tune.py` | Fine-tune the embedding model |
| `05_evaluate_improvement.py` | Compare baseline vs fine-tuned |
| `06_re_embed_products.py` | Update embeddings in PostgreSQL |
| `07_compare_search_results.py` | Test against live API |

## Environment Variables

```bash
export ANTHROPIC_API_KEY="your-api-key"
export DB_PASSWORD="your-db-password"

# macOS only - required to avoid OpenMP conflicts
export KMP_DUPLICATE_LIB_OK=TRUE
```

## Troubleshooting

### macOS: OpenMP Error

**Error:**
```
OMP: Error #15: Initializing libiomp5.dylib, but found libomp.dylib already initialized.
OMP: Hint: This means that multiple copies of the OpenMP runtime have been linked into the program.
```

**Cause:** Conflict between OpenMP libraries from PyTorch and NumPy/Anaconda on macOS.

**Solution:** Set the environment variable before running scripts:
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
python 03_baseline_evaluation.py
```

Or run inline:
```bash
KMP_DUPLICATE_LIB_OK=TRUE python 03_baseline_evaluation.py
```

To make this permanent, add to your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
echo 'export KMP_DUPLICATE_LIB_OK=TRUE' >> ~/.zshrc
source ~/.zshrc
```

---

### PIL/Pillow: Missing 'Resampling' Attribute

**Error:**
```
AttributeError: module 'PIL.Image' has no attribute 'Resampling'
```

**Cause:** Pillow version is older than 9.1.0.

**Solution:**
```bash
pip install --upgrade 'Pillow>=9.1.0'
```

---

### NumPy 2.x Compatibility Issues

**Error:**
```
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.0.x
```

**Cause:** Some packages (scipy, scikit-learn, torch) may not be compatible with NumPy 2.x.

**Solution:**
```bash
pip install 'numpy>=1.24,<2.0'
pip install --upgrade scipy scikit-learn
```

---

### urllib3/botocore Import Error

**Error:**
```
ImportError: cannot import name 'DEFAULT_CIPHERS' from 'urllib3.util.ssl_'
```

**Cause:** Version mismatch between botocore and urllib3.

**Solution:**
```bash
pip install --upgrade boto3 botocore
```

---

### accelerate Not Found

**Error:**
```
ImportError: Using the `Trainer` with `PyTorch` requires `accelerate>=0.26.0`
```

**Solution:**
```bash
pip install 'accelerate>=0.26.0'
```

---

### General: Dependency Conflicts

If you encounter multiple dependency conflicts, try a clean install:

```bash
# Create a fresh virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt
```

## Output

After running the scripts:

- `data/` - Training data, evaluation results
- `fine-tuned-all-MiniLM-L6-v2-amazon/` - The fine-tuned model
- `EVALUATION_REPORT_v1.md` - Detailed evaluation report