#!/usr/bin/env python3
"""
demo.py - Interactive Legal Fine-Tuning Demo

A guided walkthrough of the legal embedding model fine-tuning process.
Runs each step interactively, explaining what happens and showing results.
"""

import os
import sys
import json
import subprocess
import platform
from pathlib import Path

BASE_DIR = Path(__file__).parent


def clear_screen():
    os.system('cls' if platform.system() == 'Windows' else 'clear')


def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_step_header(step_num, title):
    print("\n" + "-" * 70)
    print(f"  STEP {step_num}: {title}")
    print("-" * 70 + "\n")


def prompt_continue(message="Press Enter to continue, or 'q' to quit: "):
    response = input(message).strip().lower()
    return response != 'q'


def prompt_yes_no(message):
    while True:
        response = input(message + " (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        print("Please enter 'y' or 'n'")


def run_script(script_name):
    script_path = BASE_DIR / script_name
    try:
        result = subprocess.run(
            [sys.executable, "-u", str(script_path)],
            cwd=str(BASE_DIR)
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error running {script_name}: {e}")
        return False


def run_reset(clean=False):
    args = [sys.executable, str(BASE_DIR / "reset.py")]
    if clean:
        args.append("--clean")
        result = subprocess.run(
            args, input="yes\n", text=True, capture_output=True, cwd=str(BASE_DIR)
        )
    else:
        result = subprocess.run(args, cwd=str(BASE_DIR))
    return result.returncode == 0


def load_json_file(path):
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return None


def get_latest_version():
    from version_config import get_existing_versions, set_current_version
    versions = get_existing_versions()
    if versions:
        version = max(versions)
        set_current_version(version)
        return version
    return None


def open_file(path):
    path = Path(path)
    if platform.system() == 'Darwin':
        subprocess.run(['open', str(path)])
    elif platform.system() == 'Windows':
        os.startfile(str(path))
    else:
        subprocess.run(['xdg-open', str(path)])
    print(f"Opened: {path}")


def show_welcome():
    clear_screen()
    print_header("LEGAL EMBEDDING MODEL FINE-TUNING DEMO")

    print("""
This interactive demo guides you through fine-tuning the
freelawproject/modernbert-embed-base_finetune_512 embedding model
for improved legal document search relevancy.

You'll see how legal research queries are generated, how the 768-dim
model is trained on (query, document) pairs, and how we measure the
improvement in legal search quality using NDCG@10, MRR, and Recall.

Each step will be explained before running, and you'll see the results
before moving to the next step.
""")

    from version_config import get_existing_versions
    versions = get_existing_versions()

    if versions:
        print(f"Found {len(versions)} existing version(s): {', '.join(f'v{v}' for v in versions)}")
        print()

    print("OPTIONS:")
    print("  1. Start fresh (reset all data)")
    print("  2. Start fresh (keep previous versions)")
    print("  3. View existing reports")
    print("  4. Exit")
    print()

    while True:
        choice = input("Enter your choice (1-4): ").strip()
        if choice in ['1', '2', '3', '4']:
            return int(choice)
        print("Please enter 1, 2, 3, or 4")


def show_existing_reports():
    from version_config import get_existing_versions, get_evaluation_report_path

    versions = get_existing_versions()
    reports = []
    for v in versions:
        report_path = get_evaluation_report_path(v)
        if report_path.exists():
            reports.append((v, report_path))

    if not reports:
        print("\nNo evaluation reports found.")
        input("Press Enter to continue...")
        return

    print("\nExisting Evaluation Reports:")
    print("-" * 50)
    for v, path in reports:
        print(f"  v{v}: {path.name}")
    print()

    if prompt_yes_no("Would you like to open a report?"):
        print("\nEnter version number to open (or 'q' to cancel): ", end="")
        choice = input().strip()
        if choice != 'q':
            try:
                v = int(choice)
                report_path = get_evaluation_report_path(v)
                if report_path.exists():
                    open_file(report_path)
                else:
                    print(f"Report for v{v} not found.")
            except ValueError:
                print("Invalid version number.")

    input("\nPress Enter to continue...")


def step_1_extract_documents():
    print_step_header(1, "EXTRACT LEGAL DOCUMENTS")

    print("""
What happens in this step:
- Loads 58 legal documents from legal-documents.csv
- Extracts title, citation, court, practice area, content, and headnotes
- Creates a 'searchable_content' field combining all legal text fields
- Saves structured document data for training

This creates the legal document corpus that will be used to generate
training data and evaluate search quality across case law, statutes,
regulations, and practice guides.
""")

    if not prompt_continue():
        return False

    print("\nRunning legal document extraction...\n")
    success = run_script("01_extract_legal_docs.py")

    if success:
        from version_config import get_versioned_paths, get_existing_versions, set_current_version
        versions = get_existing_versions()
        version = max(versions) if versions else 1
        set_current_version(version)
        paths = get_versioned_paths(version)

        if paths['documents'].exists():
            documents = load_json_file(paths['documents'])
            if documents:
                doc_types = set(d.get('doc_type', 'Unknown') for d in documents)
                practice_areas = set(d.get('practice_area', 'Unknown') for d in documents)

                print("\n" + "=" * 50)
                print("STEP 1 SUMMARY")
                print("=" * 50)
                print(f"  Documents extracted:    {len(documents)}")
                print(f"  Document types:         {len(doc_types)}")
                print(f"  Practice areas:         {len(practice_areas)}")
                print(f"  Data saved to:          v{version}/documents.json")
                print("=" * 50)

    return success


def step_2_generate_training_data():
    print_step_header(2, "GENERATE LEGAL RESEARCH TRAINING DATA")

    from config import USE_CLAUDE, QUERIES_PER_DOCUMENT

    mode = "Claude API (high-quality)" if USE_CLAUDE else "Rule-based (fast, no API cost)"

    print(f"""
What happens in this step:
- Generates {QUERIES_PER_DOCUMENT} diverse legal research queries per document
- Mode: {mode}
- Creates (query, document) pairs for training
- Splits data into 80% training / 20% test sets

{"Using Claude API will generate diverse, realistic legal research queries." if USE_CLAUDE else "Rule-based generation uses doc_type-specific templates (case law, statute, regulation, practice guide)."}

Query types include: issue-based, standard-of-review, elements queries,
jurisdiction-specific, procedural, and natural language research questions.
""")

    if not prompt_continue():
        return False

    print("\nGenerating legal training data...\n")
    success = run_script("02_generate_training_data.py")

    if success:
        from version_config import get_versioned_paths
        version = get_latest_version()
        paths = get_versioned_paths(version)

        train_data = load_json_file(paths['train_split'])
        test_data = load_json_file(paths['test_split'])

        if train_data and test_data:
            print("\n" + "=" * 50)
            print("STEP 2 SUMMARY")
            print("=" * 50)
            print(f"  Total pairs generated: {len(train_data) + len(test_data)}")
            print(f"  Training pairs:        {len(train_data)}")
            print(f"  Test pairs:            {len(test_data)}")
            print(f"  Generation mode:       {'Claude API' if USE_CLAUDE else 'Rule-based'}")
            print("=" * 50)

            if train_data:
                print("\nSample training pair:")
                sample = train_data[0]
                print(f"  Query:    '{sample['query']}'")
                print(f"  Document: '{sample['title'][:60]}...'")
                print(f"  Type:     {sample.get('doc_type', '')}")

    return success


def step_3_baseline_evaluation():
    print_step_header(3, "BASELINE EVALUATION")

    print("""
What happens in this step:
- Loads the base ModernBERT legal model (768 dimensions)
- Runs legal research queries from the test set
- Measures how well the model ranks relevant documents
- Establishes baseline metrics before fine-tuning

Key metrics:
- NDCG@10: How well are relevant documents ranked in top 10?
- Accuracy@1: Is the correct document ranked first?
- MRR@10: Average rank of the first relevant result

Note: This base model is already fine-tuned on US legal opinions by
Free Law Project, so the baseline should be reasonable.
""")

    if not prompt_continue():
        return False

    print("\nEvaluating baseline model...\n")
    success = run_script("03_baseline_evaluation.py")

    if success:
        from version_config import get_versioned_paths
        version = get_latest_version()
        paths = get_versioned_paths(version)

        results = load_json_file(paths['baseline_results'])

        if results:
            print("\n" + "=" * 50)
            print("STEP 3 SUMMARY - BASELINE METRICS")
            print("=" * 50)
            print(f"  NDCG@10 (primary):     {results.get('legal-documents-baseline_cosine_ndcg@10', 0):.4f}")
            print(f"  Accuracy@1:            {results.get('legal-documents-baseline_cosine_accuracy@1', 0):.4f}")
            print(f"  Accuracy@10:           {results.get('legal-documents-baseline_cosine_accuracy@10', 0):.4f}")
            print(f"  MRR@10:                {results.get('legal-documents-baseline_cosine_mrr@10', 0):.4f}")
            print("=" * 50)
            print("\nThese are the metrics we aim to improve with fine-tuning.")

    return success


def step_4_fine_tune():
    print_step_header(4, "FINE-TUNE LEGAL EMBEDDING MODEL")

    from config import TRAIN_EPOCHS, BATCH_SIZE, LEARNING_RATE

    print(f"""
What happens in this step:
- Loads the base model and legal training data
- Trains using MultipleNegativesRankingLoss
- Uses in-batch negatives (other documents in batch are negatives)
- Evaluates after each epoch and saves best model

Training configuration:
- Epochs:        {TRAIN_EPOCHS} (more epochs for smaller 58-doc corpus)
- Batch size:    {BATCH_SIZE}
- Learning rate: {LEARNING_RATE}

The model learns to place legal research queries closer to their
relevant documents in the 768-dimensional embedding space.

NOTE: This step may take 2-5 minutes on CPU.
""")

    if not prompt_continue():
        return False

    print("\nFine-tuning legal model (this may take a few minutes)...\n")
    success = run_script("04_fine_tune.py")

    if success:
        from version_config import get_versioned_paths
        version = get_latest_version()
        paths = get_versioned_paths(version)

        results = load_json_file(paths['finetuned_results'])

        if results:
            baseline = results.get('baseline', {})
            finetuned = results.get('finetuned', {})
            improvement = results.get('improvement', {})

            base_ndcg = baseline.get('legal-documents-finetune_cosine_ndcg@10', 0)
            fine_ndcg = finetuned.get('legal-documents-finetune_cosine_ndcg@10', 0)

            print("\n" + "=" * 50)
            print("STEP 4 SUMMARY - FINE-TUNING COMPLETE")
            print("=" * 50)
            print(f"  NDCG@10 before:        {base_ndcg:.4f}")
            print(f"  NDCG@10 after:         {fine_ndcg:.4f}")
            print(f"  Improvement:           {improvement.get('ndcg@10_relative_pct', 0):+.1f}%")
            print(f"  Model saved to:        v{version}/model/")
            print("=" * 50)

    return success


def step_5_evaluate_improvement():
    print_step_header(5, "EVALUATE IMPROVEMENT")

    print("""
What happens in this step:
- Loads both base and fine-tuned models
- Runs full evaluation on both
- Compares metrics side-by-side
- Shows example legal search results from both models

This produces the detailed comparison showing exactly how much
the fine-tuning improved legal search quality, with side-by-side
results showing doc_type, practice_area, and similarity scores.
""")

    if not prompt_continue():
        return False

    print("\nRunning comprehensive evaluation...\n")
    success = run_script("05_evaluate_improvement.py")

    if success:
        from version_config import get_versioned_paths
        version = get_latest_version()
        paths = get_versioned_paths(version)

        report = load_json_file(paths['comparison_report'])

        if report:
            metrics = report.get('metrics', {})
            ndcg = metrics.get('cosine_ndcg@10', {})
            acc1 = metrics.get('cosine_accuracy@1', {})
            acc10 = metrics.get('cosine_accuracy@10', {})

            print("\n" + "=" * 60)
            print("STEP 5 SUMMARY - IMPROVEMENT METRICS")
            print("=" * 60)
            print(f"{'Metric':<20} {'Baseline':>10} {'Fine-tuned':>12} {'Change':>10}")
            print("-" * 60)
            print(f"{'NDCG@10':<20} {ndcg.get('baseline', 0):>10.4f} {ndcg.get('finetuned', 0):>12.4f} {ndcg.get('pct_change', 0):>+9.1f}%")
            print(f"{'Accuracy@1':<20} {acc1.get('baseline', 0):>10.4f} {acc1.get('finetuned', 0):>12.4f} {acc1.get('pct_change', 0):>+9.1f}%")
            print(f"{'Accuracy@10':<20} {acc10.get('baseline', 0):>10.4f} {acc10.get('finetuned', 0):>12.4f} {acc10.get('pct_change', 0):>+9.1f}%")
            print("=" * 60)

    return success


def step_6_generate_report():
    print_step_header(6, "GENERATE EVALUATION REPORT")

    print("""
What happens in this step:
- Compiles all results into a professional markdown report
- Includes methodology, metrics, and search examples
- References legal-domain specifics (hybrid search, triple embeddings)
- Updates the version README with final metrics

This creates the final documentation of the legal fine-tuning run.
""")

    if not prompt_continue():
        return False

    print("\nGenerating evaluation report...\n")
    success = run_script("generate_report.py")

    return success


def show_completion():
    from version_config import get_existing_versions, get_evaluation_report_path, get_versioned_paths

    versions = get_existing_versions()
    version = None
    for v in reversed(versions):
        report_path = get_evaluation_report_path(v)
        if report_path.exists():
            version = v
            break

    if version is None:
        print("\nNo report was generated.")
        return

    report_path = get_evaluation_report_path(version)
    paths = get_versioned_paths(version)

    print_header("LEGAL FINE-TUNING DEMO COMPLETE!")

    print(f"""
Congratulations! You've successfully completed the legal fine-tuning demo.

Summary of what was accomplished:
- Extracted 58 legal documents (case law, statutes, regulations, practice guides)
- Generated ~580 legal research query training pairs
- Evaluated baseline ModernBERT legal model performance
- Fine-tuned the 768-dim embedding model
- Measured improvement in legal search quality

All data for this run is stored in: data/v{version}/
""")

    report = load_json_file(paths['comparison_report'])
    if report:
        metrics = report.get('metrics', {})
        ndcg = metrics.get('cosine_ndcg@10', {})
        print(f"Final Result: NDCG@10 improved by {ndcg.get('pct_change', 0):+.1f}%")
        print(f"              ({ndcg.get('baseline', 0):.4f} -> {ndcg.get('finetuned', 0):.4f})")

    print(f"\nEvaluation Report: {report_path}")
    print(f"Version README:    {paths['readme']}")
    print()

    if prompt_yes_no("Would you like to open the evaluation report?"):
        open_file(report_path)

    print("\nThank you for running the legal fine-tuning demo!")
    print("Run 'python demo.py' again to start a new demo run.\n")


def handle_abort():
    print("\n" + "-" * 50)
    print("Demo interrupted.")
    print("-" * 50)

    if prompt_yes_no("\nWould you like to reset and start fresh next time?"):
        print("\nResetting workspace...")
        run_reset(clean=False)
        print("Workspace reset. Run 'python demo.py' to start again.")
    else:
        print("\nWorkspace left as-is. You can continue later or reset manually.")
        print("Run 'python reset.py' to reset, or 'python demo.py' to continue.")


def main():
    try:
        while True:
            choice = show_welcome()

            if choice == 4:
                print("\nGoodbye!")
                return

            if choice == 3:
                show_existing_reports()
                continue

            if choice == 1:
                print("\nPerforming full reset...")
                run_reset(clean=True)
                print("All data cleared.\n")
            elif choice == 2:
                print("\nResetting workspace (keeping previous versions)...")
                run_reset(clean=False)
                print("Ready for new run.\n")

            input("Press Enter to begin the legal fine-tuning demo...")

            steps = [
                ("Extract Legal Documents", step_1_extract_documents),
                ("Generate Training Data", step_2_generate_training_data),
                ("Baseline Evaluation", step_3_baseline_evaluation),
                ("Fine-Tune Model", step_4_fine_tune),
                ("Evaluate Improvement", step_5_evaluate_improvement),
                ("Generate Report", step_6_generate_report),
            ]

            for name, step_func in steps:
                if not step_func():
                    handle_abort()
                    break

                if not prompt_continue(f"\nStep complete. Press Enter for next step, or 'q' to quit: "):
                    handle_abort()
                    break
            else:
                show_completion()

            if not prompt_yes_no("\nWould you like to run another demo?"):
                print("\nGoodbye!")
                break

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
        handle_abort()


if __name__ == "__main__":
    main()