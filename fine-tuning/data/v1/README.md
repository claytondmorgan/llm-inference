# Fine-Tuning Run v1

## Run Information
- **Timestamp:** 2026-02-02T17:08:24.497628
- **Version:** 1

## Configuration Parameters

| Parameter | Value |
|-----------|-------|
| TRAIN_EPOCHS | 3 |
| BATCH_SIZE | 32 |
| LEARNING_RATE | 2e-05 |
| WARMUP_RATIO | 0.1 |
| QUERIES_PER_PRODUCT | 4 |
| USE_CLAUDE | False |
| BASE_MODEL | sentence-transformers/all-MiniLM-L6-v2 |
| EMBEDDING_DIM | 384 |

## Final Evaluation Metrics

| Metric | Baseline | Fine-Tuned | Change |
|--------|----------|------------|--------|
| Accuracy@1 | 0.2188 | 0.2525 | +15.4% |
| MRR@10 | 0.2492 | 0.2898 | +16.3% |

## Files in This Version

- `products.json` - Extracted product catalog
- `training_pairs.json` - All generated (query, product) pairs
- `train_split.json` - 80% training split
- `test_split.json` - 20% test split
- `baseline_results.json` - Base model evaluation metrics
- `finetuned_results.json` - Fine-tuned model metrics
- `comparison_report.json` - Detailed comparison data
- `model/` - Fine-tuned model weights

## Evaluation Report

See `EVALUATION_REPORT_v1.md` in the project root for the full report.
