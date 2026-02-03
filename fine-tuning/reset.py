#!/usr/bin/env python3
"""
reset.py - Reset fine-tuning workspace to baseline state

This script manages the demo reset functionality, allowing you to:
- Archive current work before resetting
- Clear working directories to start fresh
- Optionally delete all versioned data for a complete reset

Usage:
    python reset.py              # Reset to baseline (keeps versioned data)
    python reset.py --archive    # Archive current work before reset
    python reset.py --clean      # Full reset (delete ALL versions) - requires confirmation
    python reset.py --list       # List all existing versions
"""

import argparse
import shutil
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CHECKPOINTS_DIR = BASE_DIR / "training-checkpoints"
LEGACY_MODEL_DIR = BASE_DIR / "fine-tuned-all-MiniLM-L6-v2-amazon"

# Files that may exist loose in data/ from legacy runs
LOOSE_DATA_FILES = [
    'products.json',
    'training_pairs.json',
    'train_split.json',
    'test_split.json',
    'baseline_results.json',
    'finetuned_results.json',
    'comparison_report.json',
    'live_search_results.json',
    'live_search_results_BEFORE.json',
]


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
    """Get next version number."""
    versions = get_existing_versions()
    if not versions:
        return 1
    return max(versions) + 1


def list_versions():
    """List all existing versions with their status."""
    versions = get_existing_versions()

    if not versions:
        print("No versioned runs found.")
        return

    print("\nExisting versions:")
    print("-" * 60)

    for v in versions:
        version_dir = DATA_DIR / f"v{v}"
        model_exists = (version_dir / "model").exists()
        results_exists = (version_dir / "finetuned_results.json").exists()
        readme_exists = (version_dir / "README.md").exists()
        report_exists = (BASE_DIR / f"EVALUATION_REPORT_v{v}.md").exists()

        status = "complete" if results_exists else "incomplete"
        model_status = "model" if model_exists else "no model"

        # Get timestamp from README if available
        timestamp = "unknown"
        if readme_exists:
            try:
                content = (version_dir / "README.md").read_text()
                for line in content.split('\n'):
                    if 'Timestamp:' in line:
                        timestamp = line.split('**')[-1].strip() if '**' in line else line.split(':')[-1].strip()
                        break
            except Exception:
                pass

        print(f"  v{v}: {status}, {model_status}, report: {'yes' if report_exists else 'no'}")

    print("-" * 60)
    print(f"Total: {len(versions)} version(s)")


def archive_current():
    """Archive loose files in data/ to a new version folder.

    Returns:
        Version number if archived, None if nothing to archive
    """
    # Check for loose files
    has_loose = any((DATA_DIR / f).exists() for f in LOOSE_DATA_FILES)
    has_legacy_model = LEGACY_MODEL_DIR.exists()

    if not has_loose and not has_legacy_model:
        print("No loose data files or legacy model to archive.")
        return None

    version = get_next_version()
    version_dir = DATA_DIR / f"v{version}"
    version_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nArchiving current work to v{version}...")

    # Move loose data files
    for f in LOOSE_DATA_FILES:
        src = DATA_DIR / f
        if src.exists():
            shutil.move(str(src), str(version_dir / f))
            print(f"  Archived data/{f} -> v{version}/")

    # Move legacy model if exists
    if has_legacy_model:
        model_dest = version_dir / "model"
        shutil.move(str(LEGACY_MODEL_DIR), str(model_dest))
        print(f"  Archived model -> v{version}/model/")

    # Archive non-versioned report
    report_src = BASE_DIR / "EVALUATION_REPORT.md"
    if report_src.exists():
        report_dest = BASE_DIR / f"EVALUATION_REPORT_v{version}.md"
        shutil.move(str(report_src), str(report_dest))
        print(f"  Archived report -> EVALUATION_REPORT_v{version}.md")

    # Create a basic README for archived version
    readme_path = version_dir / "README.md"
    if not readme_path.exists():
        readme_content = f"""# Fine-Tuning Run v{version}

## Run Information
- **Timestamp:** {datetime.now().isoformat()}
- **Version:** {version}
- **Note:** This version was created by archiving loose files from a legacy run.

## Configuration Parameters

*(Configuration unknown - archived from legacy run)*

## Final Evaluation Metrics

*(Check finetuned_results.json if available)*
"""
        readme_path.write_text(readme_content)
        print(f"  Created README for v{version}")

    print(f"\nArchived current work as version {version}")
    return version


def reset_workspace(full_clean=False):
    """Reset workspace to baseline state.

    Args:
        full_clean: If True, delete ALL versioned data (requires confirmation)
    """
    print("\nResetting workspace...")

    # Delete training checkpoints (always, saves ~519MB)
    if CHECKPOINTS_DIR.exists():
        size_mb = sum(f.stat().st_size for f in CHECKPOINTS_DIR.rglob('*') if f.is_file()) / (1024 * 1024)
        shutil.rmtree(CHECKPOINTS_DIR)
        print(f"  Deleted training-checkpoints/ ({size_mb:.1f}MB)")

    # Delete legacy model location
    if LEGACY_MODEL_DIR.exists():
        size_mb = sum(f.stat().st_size for f in LEGACY_MODEL_DIR.rglob('*') if f.is_file()) / (1024 * 1024)
        shutil.rmtree(LEGACY_MODEL_DIR)
        print(f"  Deleted fine-tuned-all-MiniLM-L6-v2-amazon/ ({size_mb:.1f}MB)")

    # Delete loose data files
    for f in LOOSE_DATA_FILES:
        path = DATA_DIR / f
        if path.exists():
            path.unlink()
            print(f"  Deleted data/{f}")

    # Delete non-versioned report
    report_path = BASE_DIR / "EVALUATION_REPORT.md"
    if report_path.exists():
        report_path.unlink()
        print("  Deleted EVALUATION_REPORT.md")

    # Full clean: delete ALL versions
    if full_clean:
        versions = get_existing_versions()
        for v in versions:
            version_dir = DATA_DIR / f"v{v}"
            if version_dir.exists():
                shutil.rmtree(version_dir)
                print(f"  Deleted data/v{v}/")

            # Remove versioned reports
            report = BASE_DIR / f"EVALUATION_REPORT_v{v}.md"
            if report.exists():
                report.unlink()
                print(f"  Deleted EVALUATION_REPORT_v{v}.md")

    print("\nWorkspace reset to baseline state.")
    if not full_clean:
        versions = get_existing_versions()
        if versions:
            print(f"Preserved {len(versions)} versioned run(s): {', '.join(f'v{v}' for v in versions)}")


def main():
    parser = argparse.ArgumentParser(
        description="Reset fine-tuning workspace for demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python reset.py              # Quick reset, keeps versioned data
    python reset.py --archive    # Archive current work, then reset
    python reset.py --clean      # Delete everything (asks for confirmation)
    python reset.py --list       # Show all existing versions
        """
    )
    parser.add_argument(
        '--archive', '-a',
        action='store_true',
        help='Archive current work to a new version before reset'
    )
    parser.add_argument(
        '--clean', '-c',
        action='store_true',
        help='Full reset - delete ALL versions (requires confirmation)'
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all existing versions'
    )

    args = parser.parse_args()

    if args.list:
        list_versions()
        return

    if args.clean:
        versions = get_existing_versions()
        if versions:
            print(f"\nWARNING: This will delete ALL {len(versions)} versioned run(s):")
            for v in versions:
                print(f"  - v{v}")
            print()
            confirm = input("Type 'yes' to confirm deletion: ")
            if confirm.lower() != 'yes':
                print("Aborted.")
                return
        else:
            print("No versioned data to delete.")

    if args.archive:
        archive_current()

    reset_workspace(full_clean=args.clean)

    print("\nReady for a fresh fine-tuning run!")
    print("Run: python 01_extract_products.py to start")


if __name__ == "__main__":
    main()