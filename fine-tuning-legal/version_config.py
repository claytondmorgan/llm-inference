#!/usr/bin/env python3
"""
version_config.py - Version management for legal fine-tuning demo
"""

import os
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

_current_version = None


def get_existing_versions():
    if not DATA_DIR.exists():
        return []
    existing = [
        d.name for d in DATA_DIR.iterdir()
        if d.is_dir() and d.name.startswith('v') and d.name[1:].isdigit()
    ]
    return sorted([int(d[1:]) for d in existing])


def get_next_version():
    versions = get_existing_versions()
    if not versions:
        return 1
    return max(versions) + 1


def get_current_version():
    global _current_version
    return _current_version


def set_current_version(version):
    global _current_version
    _current_version = version


def get_version_dir(version=None):
    if version is None:
        version = get_current_version()
        if version is None:
            raise ValueError("No version set. Call initialize_new_version() first.")
    return DATA_DIR / f"v{version}"


def get_versioned_paths(version=None):
    version_dir = get_version_dir(version)
    return {
        'version_dir': version_dir,
        'documents': version_dir / "documents.json",
        'training_pairs': version_dir / "training_pairs.json",
        'train_split': version_dir / "train_split.json",
        'test_split': version_dir / "test_split.json",
        'baseline_results': version_dir / "baseline_results.json",
        'finetuned_results': version_dir / "finetuned_results.json",
        'comparison_report': version_dir / "comparison_report.json",
        'model_dir': version_dir / "model",
        'readme': version_dir / "README.md",
    }


def initialize_new_version():
    version = get_next_version()
    set_current_version(version)
    version_dir = get_version_dir(version)
    version_dir.mkdir(parents=True, exist_ok=True)
    print(f"Initialized new version: v{version}")
    print(f"Data will be stored in: {version_dir}")
    return version


def get_config_snapshot():
    import config
    return {
        'TRAIN_EPOCHS': getattr(config, 'TRAIN_EPOCHS', 5),
        'BATCH_SIZE': getattr(config, 'BATCH_SIZE', 16),
        'LEARNING_RATE': getattr(config, 'LEARNING_RATE', 2e-5),
        'WARMUP_RATIO': getattr(config, 'WARMUP_RATIO', 0.1),
        'QUERIES_PER_DOCUMENT': getattr(config, 'QUERIES_PER_DOCUMENT', 10),
        'USE_CLAUDE': getattr(config, 'USE_CLAUDE', False),
        'BASE_MODEL': getattr(config, 'BASE_MODEL', 'freelawproject/modernbert-embed-base_finetune_512'),
        'EMBEDDING_DIM': getattr(config, 'EMBEDDING_DIM', 768),
        'FINE_TUNE_ON': getattr(config, 'FINE_TUNE_ON', 'content'),
    }


def create_version_readme(version=None, config_snapshot=None, metrics=None):
    if version is None:
        version = get_current_version()
    if config_snapshot is None:
        config_snapshot = get_config_snapshot()

    paths = get_versioned_paths(version)
    timestamp = datetime.now().isoformat()

    content = f"""# Legal Fine-Tuning Run v{version}

## Run Information
- **Timestamp:** {timestamp}
- **Version:** {version}

## Configuration Parameters

| Parameter | Value |
|-----------|-------|
| TRAIN_EPOCHS | {config_snapshot.get('TRAIN_EPOCHS', 'N/A')} |
| BATCH_SIZE | {config_snapshot.get('BATCH_SIZE', 'N/A')} |
| LEARNING_RATE | {config_snapshot.get('LEARNING_RATE', 'N/A')} |
| WARMUP_RATIO | {config_snapshot.get('WARMUP_RATIO', 'N/A')} |
| QUERIES_PER_DOCUMENT | {config_snapshot.get('QUERIES_PER_DOCUMENT', 'N/A')} |
| USE_CLAUDE | {config_snapshot.get('USE_CLAUDE', 'N/A')} |
| BASE_MODEL | {config_snapshot.get('BASE_MODEL', 'N/A')} |
| EMBEDDING_DIM | {config_snapshot.get('EMBEDDING_DIM', 'N/A')} |
| FINE_TUNE_ON | {config_snapshot.get('FINE_TUNE_ON', 'N/A')} |

## Final Evaluation Metrics

"""

    if metrics:
        content += """| Metric | Baseline | Fine-Tuned | Change |
|--------|----------|------------|--------|
"""
        if 'baseline_ndcg10' in metrics:
            content += f"| NDCG@10 | {metrics.get('baseline_ndcg10', 'N/A')} | {metrics.get('finetuned_ndcg10', 'N/A')} | {metrics.get('ndcg10_change', 'N/A')} |\n"
        if 'baseline_acc1' in metrics:
            content += f"| Accuracy@1 | {metrics.get('baseline_acc1', 'N/A')} | {metrics.get('finetuned_acc1', 'N/A')} | {metrics.get('acc1_change', 'N/A')} |\n"
        if 'baseline_mrr10' in metrics:
            content += f"| MRR@10 | {metrics.get('baseline_mrr10', 'N/A')} | {metrics.get('finetuned_mrr10', 'N/A')} | {metrics.get('mrr10_change', 'N/A')} |\n"
    else:
        content += "*(Run evaluation scripts to populate metrics)*\n"

    content += f"""
## Files in This Version

- `documents.json` - Extracted legal documents
- `training_pairs.json` - All generated (query, document) pairs
- `train_split.json` - 80% training split
- `test_split.json` - 20% test split
- `baseline_results.json` - Base model evaluation metrics
- `finetuned_results.json` - Fine-tuned model metrics
- `comparison_report.json` - Detailed comparison data
- `model/` - Fine-tuned model weights

## Evaluation Report

See `EVALUATION_REPORT_v{version}.md` in the project root for the full report.
"""

    paths['readme'].write_text(content)
    print(f"Created README for v{version}")
    return paths['readme']


def update_version_readme_with_metrics(version=None, metrics=None):
    if version is None:
        version = get_current_version()
    config_snapshot = get_config_snapshot()
    create_version_readme(version, config_snapshot, metrics)


def get_evaluation_report_path(version=None):
    if version is None:
        version = get_current_version()
    return BASE_DIR / f"EVALUATION_REPORT_v{version}.md"


def load_version(version):
    version_dir = DATA_DIR / f"v{version}"
    if not version_dir.exists():
        print(f"Version v{version} does not exist")
        return False
    set_current_version(version)
    print(f"Loaded version: v{version}")
    return True


def detect_or_create_version():
    versions = get_existing_versions()
    if versions:
        latest = max(versions)
        paths = get_versioned_paths(latest)
        if paths['documents'].exists() and not paths['comparison_report'].exists():
            set_current_version(latest)
            print(f"Continuing existing version: v{latest}")
            return latest
    return initialize_new_version()