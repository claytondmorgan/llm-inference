# Legal Embedding Fine-Tuning Demo

Fine-tune the `freelawproject/modernbert-embed-base_finetune_512` (768-dim) embedding model for improved legal document search relevancy.

## Quick Start

```bash
cd fine-tuning-legal
pip install -r requirements.txt

# Interactive demo (recommended)
python demo.py

# Or run steps individually
python 01_extract_legal_docs.py
python 02_generate_training_data.py
python 03_baseline_evaluation.py
python 04_fine_tune.py
python 05_evaluate_improvement.py
python generate_report.py
```

## Pipeline Overview

| Step | Script | Description |
|------|--------|-------------|
| 1 | `01_extract_legal_docs.py` | Extract 58 legal documents from CSV |
| 2 | `02_generate_training_data.py` | Generate ~580 legal research queries (10/doc) |
| 3 | `03_baseline_evaluation.py` | Evaluate base ModernBERT legal model |
| 4 | `04_fine_tune.py` | Fine-tune with MultipleNegativesRankingLoss |
| 5 | `05_evaluate_improvement.py` | Compare base vs fine-tuned model |
| 6 | `06_re_embed_legal_docs.py` | Update triple embeddings in live database |
| 7 | `07_compare_search_results.py` | Test live /legal/search endpoint |

## Configuration

Edit `config.py` to adjust:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BASE_MODEL` | `freelawproject/modernbert-embed-base_finetune_512` | 768-dim legal embedding model |
| `TRAIN_EPOCHS` | 5 | More epochs for smaller dataset |
| `BATCH_SIZE` | 16 | Smaller batch for ~580 training pairs |
| `LEARNING_RATE` | 2e-5 | AdamW learning rate |
| `QUERIES_PER_DOCUMENT` | 10 | Queries generated per document |
| `USE_CLAUDE` | False | Use Claude API for query generation |

## Training Data

Legal research queries are generated using doc_type-specific templates:

- **Case law**: Issue-based, standard-of-review, elements, jurisdiction queries
- **Statutes**: Statutory requirements, protected classes, definitions, penalties
- **Regulations**: Compliance, enforcement, agency guidance queries
- **Practice guides**: How-to, checklist, best practices, prevention queries

Set `USE_CLAUDE=True` in config.py to use Claude API for higher-quality query generation.

## Differences from Product Demo

| Aspect | Product (`fine-tuning/`) | Legal (`fine-tuning-legal/`) |
|--------|--------------------------|------------------------------|
| Base model | all-MiniLM-L6-v2 (384-dim) | ModernBERT legal (768-dim) |
| Corpus | 1,013 Amazon products | 58 legal documents |
| Queries/doc | 4 (~4,052 total) | 10 (~580 total) |
| Epochs | 3 | 5 |
| Batch size | 32 | 16 |
| Embeddings | 2 (content, title) | 3 (content, title, headnote) |
| DB access | Direct env vars | AWS Secrets Manager |
| Search API | /search/records | /legal/search |

## Version Management

Each run creates a versioned directory under `data/`:

```
data/
├── v1/
│   ├── documents.json
│   ├── training_pairs.json
│   ├── train_split.json
│   ├── test_split.json
│   ├── baseline_results.json
│   ├── finetuned_results.json
│   ├── comparison_report.json
│   ├── model/
│   └── README.md
├── v2/
│   └── ...
```

Use `python reset.py --list` to view versions, `python reset.py --clean` for full reset.