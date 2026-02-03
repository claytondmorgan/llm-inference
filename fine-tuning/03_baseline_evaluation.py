#!/usr/bin/env python3
"""
03_baseline_evaluation.py - Evaluate the base model before fine-tuning

Measures the retrieval performance of the base all-MiniLM-L6-v2 model
using standard information retrieval metrics (NDCG@10, MRR@10, etc.)
to establish a baseline for comparison after fine-tuning.
"""

import json
import os
import sys
import numpy as np
from sentence_transformers import SentenceTransformer
from sentence_transformers.evaluation import InformationRetrievalEvaluator
from sentence_transformers.util import cos_sim
from config import BASE_MODEL
from version_config import get_versioned_paths, get_current_version, detect_or_create_version


def run_example_queries(model, products):
    """Run example queries and show top-3 results for each."""
    test_queries = [
        "gift for someone who loves cooking",
        "comfortable running shoes for men",
        "budget friendly electronics for kids",
        "waterproof jacket for hiking in rain",
        "wireless noise cancelling headphones",
    ]

    # Encode all product searchable_content
    print("\nEncoding product corpus for example queries...")
    corpus_texts = [p["searchable_content"] for p in products]
    corpus_embeddings = model.encode(corpus_texts, show_progress_bar=True, convert_to_tensor=True)

    print("\n" + "-"*60)
    print("EXAMPLE QUERY RESULTS")
    print("-"*60)

    for query in test_queries:
        query_embedding = model.encode(query, convert_to_tensor=True)
        similarities = cos_sim(query_embedding, corpus_embeddings)[0].cpu().numpy()

        # Get top 3 indices
        top_indices = np.argsort(similarities)[::-1][:3]

        print(f'\nQuery: "{query}"')
        for rank, idx in enumerate(top_indices, 1):
            title = products[idx]["title"][:50]
            sim = similarities[idx]
            print(f"  {rank}. [{sim:.3f}] {title}...")


def main():
    # Get versioned paths
    version = get_current_version()
    if version is None:
        version = detect_or_create_version()

    paths = get_versioned_paths(version)
    print(f"\n{'='*60}")
    print(f"BASELINE EVALUATION (v{version})")
    print(f"{'='*60}")

    # Check if required files exist
    if not paths['test_split'].exists():
        print(f"ERROR: Test split file not found at {paths['test_split']}")
        print("Please run 02_generate_training_data.py first.")
        sys.exit(1)

    if not paths['products'].exists():
        print(f"ERROR: Products file not found at {paths['products']}")
        print("Please run 01_extract_products.py first.")
        sys.exit(1)

    # Load data
    with open(paths['test_split'], "r") as f:
        test_data = json.load(f)

    with open(paths['products'], "r") as f:
        products = json.load(f)

    print(f"Loaded {len(test_data)} test pairs and {len(products)} products")

    # Load the base model
    print(f"\nLoading base model: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL)
    print("Model loaded successfully!")

    # Build evaluation data structures
    print("\nBuilding evaluation data structures...")

    # Corpus: ALL products (not just test products)
    corpus = {}
    for product in products:
        corpus[str(product["id"])] = product["searchable_content"]

    # Queries: from test split
    queries = {}
    for i, pair in enumerate(test_data):
        queries[f"q{i}"] = pair["query"]

    # Relevant docs: mapping from query_id to set of relevant corpus_ids
    relevant_docs = {}
    for i, pair in enumerate(test_data):
        relevant_docs[f"q{i}"] = {str(pair["product_id"])}

    print(f"  Corpus size:    {len(corpus)} documents")
    print(f"  Query count:    {len(queries)} queries")

    # Create evaluator
    evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="amazon-products-baseline",
        mrr_at_k=[1, 5, 10],
        ndcg_at_k=[5, 10],
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[5, 10],
        score_functions={"cosine": cos_sim},
        main_score_function="cosine",
        show_progress_bar=True,
        batch_size=64
    )

    # Run evaluation
    print("\nRunning baseline evaluation...")
    results = evaluator(model)

    # Print formatted results
    # Note: InformationRetrievalEvaluator prefixes keys with evaluator name
    prefix = "amazon-products-baseline_"

    print("\n" + "="*60)
    print("BASELINE EVALUATION - all-MiniLM-L6-v2 (before fine-tuning)")
    print("="*60)
    print(f"Corpus size:    {len(corpus):,} products")
    print(f"Test queries:   {len(queries):,} queries")
    print()
    print("RANKING QUALITY:")
    print(f"  NDCG@5:       {results.get(f'{prefix}cosine_ndcg@5', 0):.4f}")
    print(f"  NDCG@10:      {results.get(f'{prefix}cosine_ndcg@10', 0):.4f}    <- PRIMARY METRIC")
    print()
    print("FIRST RELEVANT RESULT:")
    print(f"  MRR@1:        {results.get(f'{prefix}cosine_mrr@1', 0):.4f}")
    print(f"  MRR@5:        {results.get(f'{prefix}cosine_mrr@5', 0):.4f}")
    print(f"  MRR@10:       {results.get(f'{prefix}cosine_mrr@10', 0):.4f}")
    print()
    print("HIT RATE (correct product in top-k):")
    print(f"  Accuracy@1:   {results.get(f'{prefix}cosine_accuracy@1', 0):.4f}    (top result is correct)")
    print(f"  Accuracy@3:   {results.get(f'{prefix}cosine_accuracy@3', 0):.4f}")
    print(f"  Accuracy@5:   {results.get(f'{prefix}cosine_accuracy@5', 0):.4f}")
    print(f"  Accuracy@10:  {results.get(f'{prefix}cosine_accuracy@10', 0):.4f}")
    print()
    print("COVERAGE:")
    print(f"  Recall@5:     {results.get(f'{prefix}cosine_recall@5', 0):.4f}")
    print(f"  Recall@10:    {results.get(f'{prefix}cosine_recall@10', 0):.4f}")
    print("="*60)

    # Save results
    # Convert any numpy values to Python types for JSON serialization
    serializable_results = {}
    for k, v in results.items():
        if hasattr(v, 'item'):
            serializable_results[k] = v.item()
        else:
            serializable_results[k] = v

    with open(paths['baseline_results'], "w") as f:
        json.dump(serializable_results, f, indent=2)
    print(f"\nResults saved to {paths['baseline_results']}")

    # Run example queries
    run_example_queries(model, products)

    print("\n" + "="*60)
    print("Baseline evaluation complete!")
    print("="*60)


if __name__ == "__main__":
    main()