#!/usr/bin/env python3
"""
version_config.py - Version management utilities for fine-tuning demo

This module provides functions for managing versioned runs of the fine-tuning
pipeline, allowing the demo to be reset and re-run with all artifacts preserved.
"""

import os
import json
from datetime import datetime
from pathlib import Path

# Base directory is the directory containing this file
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# File to track current active version during a run
_current_version = None


def get_existing_versions():
    """Get list of existing version numbers."""
    if not DATA_DIR.exists():
        return []
    existing = [
        d.name for d in DATA_DIR.iterdir()
        if d.is_dir() and d.name.startswith('v') and d.name[1:].isdigit()
    ]
    return sorted([int(d[1:]) for d in existing])


def get_next_version():
    """Scan data folder for existing version directories and return next version number."""
    versions = get_existing_versions()
    if not versions:
        return 1
    return max(versions) + 1


def get_current_version():
    """Get current version number being used in this session."""
    global _current_version
    return _current_version


def set_current_version(version):
    """Set the current version for this session."""
    global _current_version
    _current_version = version


def get_version_dir(version=None):
    """Get path to version directory."""
    if version is None:
        version = get_current_version()
        if version is None:
            raise ValueError("No version set. Call initialize_new_version() first.")
    return DATA_DIR / f"v{version}"


def get_versioned_paths(version=None):
    """Return all versioned paths for a given version.

    Returns a dict with paths for:
    - version_dir: The version directory itself
    - products: products.json
    - training_pairs: training_pairs.json
    - train_split: train_split.json
    - test_split: test_split.json
    - baseline_results: baseline_results.json
    - finetuned_results: finetuned_results.json
    - comparison_report: comparison_report.json
    - model_dir: model/ directory for fine-tuned model
    - readme: README.md for the version
    """
    version_dir = get_version_dir(version)
    return {
        'version_dir': version_dir,
        'products': version_dir / "products.json",
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
    """Initialize a new version for a fresh run.

    Creates the version directory and returns the version number.
    """
    version = get_next_version()
    set_current_version(version)

    version_dir = get_version_dir(version)
    version_dir.mkdir(parents=True, exist_ok=True)

    print(f"Initialized new version: v{version}")
    print(f"Data will be stored in: {version_dir}")

    return version


def get_config_snapshot():
    """Get a snapshot of current configuration parameters."""
    # Import config here to avoid circular imports
    import config

    return {
        'TRAIN_EPOCHS': getattr(config, 'TRAIN_EPOCHS', 3),
        'BATCH_SIZE': getattr(config, 'BATCH_SIZE', 32),
        'LEARNING_RATE': getattr(config, 'LEARNING_RATE', 2e-5),
        'WARMUP_RATIO': getattr(config, 'WARMUP_RATIO', 0.1),
        'QUERIES_PER_PRODUCT': getattr(config, 'QUERIES_PER_PRODUCT', 4),
        'USE_CLAUDE': getattr(config, 'USE_CLAUDE', False),
        'BASE_MODEL': getattr(config, 'BASE_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'),
        'EMBEDDING_DIM': getattr(config, 'EMBEDDING_DIM', 384),
    }


def create_version_readme(version=None, config_snapshot=None, metrics=None):
    """Generate README.md for a version folder.

    Args:
        version: Version number (uses current if None)
        config_snapshot: Dict of config parameters (auto-generated if None)
        metrics: Dict with evaluation metrics (optional, can be updated later)
    """
    if version is None:
        version = get_current_version()

    if config_snapshot is None:
        config_snapshot = get_config_snapshot()

    paths = get_versioned_paths(version)
    timestamp = datetime.now().isoformat()

    content = f"""# Fine-Tuning Run v{version}

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
| QUERIES_PER_PRODUCT | {config_snapshot.get('QUERIES_PER_PRODUCT', 'N/A')} |
| USE_CLAUDE | {config_snapshot.get('USE_CLAUDE', 'N/A')} |
| BASE_MODEL | {config_snapshot.get('BASE_MODEL', 'N/A')} |
| EMBEDDING_DIM | {config_snapshot.get('EMBEDDING_DIM', 'N/A')} |

## Final Evaluation Metrics

"""

    if metrics:
        content += """| Metric | Baseline | Fine-Tuned | Change |
|--------|----------|------------|--------|
"""
        if 'ndcg10' in metrics:
            content += f"| NDCG@10 | {metrics.get('baseline_ndcg10', 'N/A')} | {metrics.get('finetuned_ndcg10', 'N/A')} | {metrics.get('ndcg10_change', 'N/A')} |\n"
        if 'acc1' in metrics or 'baseline_acc1' in metrics:
            content += f"| Accuracy@1 | {metrics.get('baseline_acc1', 'N/A')} | {metrics.get('finetuned_acc1', 'N/A')} | {metrics.get('acc1_change', 'N/A')} |\n"
        if 'mrr10' in metrics or 'baseline_mrr10' in metrics:
            content += f"| MRR@10 | {metrics.get('baseline_mrr10', 'N/A')} | {metrics.get('finetuned_mrr10', 'N/A')} | {metrics.get('mrr10_change', 'N/A')} |\n"
    else:
        content += "*(Run evaluation scripts to populate metrics)*\n"

    content += f"""
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

See `EVALUATION_REPORT_v{version}.md` in the project root for the full report.
"""

    paths['readme'].write_text(content)
    print(f"Created README for v{version}")
    return paths['readme']


def update_version_readme_with_metrics(version=None, metrics=None):
    """Update the version README with final evaluation metrics.

    Args:
        version: Version number (uses current if None)
        metrics: Dict with keys like:
            - baseline_ndcg10, finetuned_ndcg10, ndcg10_change
            - baseline_acc1, finetuned_acc1, acc1_change
            - baseline_mrr10, finetuned_mrr10, mrr10_change
    """
    if version is None:
        version = get_current_version()

    # Re-create the README with metrics
    config_snapshot = get_config_snapshot()
    create_version_readme(version, config_snapshot, metrics)


def get_evaluation_report_path(version=None):
    """Get path for versioned evaluation report."""
    if version is None:
        version = get_current_version()
    return BASE_DIR / f"EVALUATION_REPORT_v{version}.md"


def load_version(version):
    """Load an existing version (for evaluation or comparison).

    Args:
        version: Version number to load

    Returns:
        True if version exists and was loaded, False otherwise
    """
    version_dir = DATA_DIR / f"v{version}"
    if not version_dir.exists():
        print(f"Version v{version} does not exist")
        return False

    set_current_version(version)
    print(f"Loaded version: v{version}")
    return True


def detect_or_create_version():
    """Detect if we should continue an existing run or start fresh.

    If the latest version is incomplete (has products but no comparison_report),
    continue that version. Otherwise, create a new version.

    Returns:
        version number
    """
    versions = get_existing_versions()

    if versions:
        # Check if the latest version is incomplete (has products but no comparison_report)
        latest = max(versions)
        paths = get_versioned_paths(latest)

        if paths['products'].exists() and not paths['comparison_report'].exists():
            # Continue incomplete version
            set_current_version(latest)
            print(f"Continuing existing version: v{latest}")
            return latest

    # Start fresh
    return initialize_new_version()