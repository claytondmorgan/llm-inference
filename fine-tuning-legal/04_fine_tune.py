#!/usr/bin/env python3
"""
04_fine_tune.py - Fine-tune the legal embedding model

Fine-tunes the freelawproject/modernbert-embed-base_finetune_512 embedding model
using MultipleNegativesRankingLoss on synthetic (query, document) pairs.
Uses in-batch negatives to learn better query-document alignment in the embedding space.
"""

import json
import os
import sys
from datasets import Dataset
from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer, SentenceTransformerTrainingArguments
from sentence_transformers.losses import MultipleNegativesRankingLoss
from sentence_transformers.evaluation import InformationRetrievalEvaluator
from sentence_transformers.util import cos_sim

sys.path.insert(0, os.path.dirname(__file__))
from config import BASE_MODEL, TRAIN_EPOCHS, BATCH_SIZE, LEARNING_RATE, WARMUP_RATIO
from version_config import get_versioned_paths, get_current_version, detect_or_create_version


def main():
    version = get_current_version()
    if version is None:
        version = detect_or_create_version()

    paths = get_versioned_paths(version)
    print(f"\n{'='*60}")
    print(f"FINE-TUNING - Legal Embedding Model (v{version})")
    print(f"{'='*60}")

    # Check required files
    for path, name in [
        (paths['train_split'], "Train split"),
        (paths['test_split'], "Test split"),
        (paths['documents'], "Documents"),
    ]:
        if not path.exists():
            print(f"ERROR: {name} file not found at {path}")
            print("Please run the previous scripts first.")
            sys.exit(1)

    # Load data
    with open(paths['train_split'], "r") as f:
        train_data = json.load(f)

    with open(paths['test_split'], "r") as f:
        test_data = json.load(f)

    with open(paths['documents'], "r") as f:
        documents = json.load(f)

    print(f"Loaded {len(train_data)} training pairs")
    print(f"Loaded {len(test_data)} test pairs")
    print(f"Loaded {len(documents)} legal documents")

    # Load base model
    print(f"\nLoading base model: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL)
    print("Model loaded successfully!")

    # Convert training data to HuggingFace Dataset
    train_dataset = Dataset.from_dict({
        "anchor": [pair["query"] for pair in train_data],
        "positive": [pair["positive"] for pair in train_data],
    })

    print(f"\nTraining dataset: {len(train_dataset)} pairs")
    print("Sample pair:")
    print(f"  Query:    '{train_data[0]['query']}'")
    print(f"  Document: '{train_data[0]['positive'][:100]}...'")

    # Build evaluation data structures
    print("\nBuilding evaluation infrastructure...")

    corpus = {}
    for doc in documents:
        corpus[str(doc["id"])] = doc["content"]

    queries = {}
    relevant_docs = {}
    for i, pair in enumerate(test_data):
        queries[f"q{i}"] = pair["query"]
        relevant_docs[f"q{i}"] = {str(pair["document_id"])}

    # Create evaluator
    evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="legal-documents-finetune",
        mrr_at_k=[1, 5, 10],
        ndcg_at_k=[5, 10],
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[5, 10],
        score_functions={"cosine": cos_sim},
        main_score_function="cosine",
        show_progress_bar=True,
        batch_size=64
    )

    prefix = "legal-documents-finetune_"

    print("\nEvaluating baseline before fine-tuning...")
    baseline_results = evaluator(model)
    baseline_ndcg = baseline_results.get(f"{prefix}cosine_ndcg@10", 0)
    print(f"Baseline NDCG@10: {baseline_ndcg:.4f}")

    # Create loss function
    loss = MultipleNegativesRankingLoss(model)

    # Calculate training steps
    steps_per_epoch = len(train_dataset) // BATCH_SIZE
    total_steps = steps_per_epoch * TRAIN_EPOCHS

    print(f"\n{'='*60}")
    print("STARTING FINE-TUNING")
    print(f"{'='*60}")
    print(f"Base model:           {BASE_MODEL}")
    print(f"Epochs:               {TRAIN_EPOCHS}")
    print(f"Batch size:           {BATCH_SIZE}")
    print(f"Learning rate:        {LEARNING_RATE}")
    print(f"Warmup ratio:         {WARMUP_RATIO}")
    print(f"Steps per epoch:      ~{steps_per_epoch}")
    print(f"Total training steps: ~{total_steps}")
    print(f"{'='*60}")

    # Configure training arguments
    training_dir = os.path.join(os.path.dirname(__file__), "training-checkpoints")
    args = SentenceTransformerTrainingArguments(
        output_dir=training_dir,
        num_train_epochs=TRAIN_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        fp16=False,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=10,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="legal-documents-finetune_cosine_ndcg@10",
        report_to="none",
    )

    # Create trainer
    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        loss=loss,
        evaluator=evaluator,
    )

    # Train
    print("\nStarting training...")
    trainer.train()

    # Final evaluation
    print("\nEvaluating fine-tuned model...")
    finetuned_results = evaluator(model)
    finetuned_ndcg = finetuned_results.get(f"{prefix}cosine_ndcg@10", 0)
    print(f"Fine-tuned NDCG@10: {finetuned_ndcg:.4f}")

    # Save the fine-tuned model
    model_dir = paths['model_dir']
    model_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(model_dir))
    print(f"\nModel saved to: {model_dir}")

    # Print summary
    improvement = finetuned_ndcg - baseline_ndcg
    pct_improvement = (improvement / baseline_ndcg * 100) if baseline_ndcg > 0 else 0

    print(f"\n{'='*60}")
    print("FINE-TUNING COMPLETE")
    print(f"{'='*60}")
    print(f"NDCG@10: {baseline_ndcg:.4f} -> {finetuned_ndcg:.4f} ({improvement:+.4f}, {pct_improvement:+.1f}%)")
    print(f"{'='*60}")

    # Save results
    def convert_results(results):
        converted = {}
        for k, v in results.items():
            if hasattr(v, 'item'):
                converted[k] = v.item()
            else:
                converted[k] = v
        return converted

    combined_results = {
        "baseline": convert_results(baseline_results),
        "finetuned": convert_results(finetuned_results),
        "improvement": {
            "ndcg@10_absolute": improvement,
            "ndcg@10_relative_pct": pct_improvement
        }
    }

    with open(paths['finetuned_results'], "w") as f:
        json.dump(combined_results, f, indent=2)
    print(f"\nResults saved to {paths['finetuned_results']}")


if __name__ == "__main__":
    main()