#!/usr/bin/env python3
"""
03_baseline_evaluation.py - Evaluate the base ModernBERT legal model before fine-tuning

Measures retrieval performance of the base freelawproject/modernbert-embed-base_finetune_512
model using standard IR metrics (NDCG@10, MRR@10, etc.) to establish a baseline.
"""

import json
import os
import sys
import numpy as np
from sentence_transformers import SentenceTransformer
from sentence_transformers.evaluation import InformationRetrievalEvaluator
from sentence_transformers.util import cos_sim

sys.path.insert(0, os.path.dirname(__file__))
from config import BASE_MODEL
from version_config import get_versioned_paths, get_current_version, detect_or_create_version


def run_example_queries(model, documents):
    """Run example queries and show top-3 results for each."""
    test_queries = [
        "hostile work environment standard",
        "ADA reasonable accommodation requirements",
        "Section 1983 civil rights claim elements",
        "exclusionary rule fourth amendment",
        "employer retaliation whistleblower protection",
    ]

    print("\nEncoding legal document corpus for example queries...")
    corpus_texts = [d["content"] for d in documents]
    corpus_embeddings = model.encode(corpus_texts, show_progress_bar=True, convert_to_tensor=True)

    print("\n" + "-"*60)
    print("EXAMPLE QUERY RESULTS")
    print("-"*60)

    for query in test_queries:
        query_embedding = model.encode(query, convert_to_tensor=True)
        similarities = cos_sim(query_embedding, corpus_embeddings)[0].cpu().numpy()

        top_indices = np.argsort(similarities)[::-1][:3]

        print(f'\nQuery: "{query}"')
        for rank, idx in enumerate(top_indices, 1):
            title = documents[idx]["title"][:55]
            doc_type = documents[idx]["doc_type"]
            sim = similarities[idx]
            print(f"  {rank}. [{sim:.3f}] [{doc_type}] {title}...")


def main():
    version = get_current_version()
    if version is None:
        version = detect_or_create_version()

    paths = get_versioned_paths(version)
    print(f"\n{'='*60}")
    print(f"BASELINE EVALUATION - Legal Documents (v{version})")
    print(f"{'='*60}")

    if not paths['test_split'].exists():
        print(f"ERROR: Test split not found. Run 02_generate_training_data.py first.")
        sys.exit(1)

    if not paths['documents'].exists():
        print(f"ERROR: Documents not found. Run 01_extract_legal_docs.py first.")
        sys.exit(1)

    with open(paths['test_split'], "r") as f:
        test_data = json.load(f)

    with open(paths['documents'], "r") as f:
        documents = json.load(f)

    print(f"Loaded {len(test_data)} test pairs and {len(documents)} legal documents")

    print(f"\nLoading base model: {BASE_MODEL}")
    model = SentenceTransformer(BASE_MODEL)
    print("Model loaded successfully!")

    print("\nBuilding evaluation data structures...")

    # Corpus: all legal documents (using content field)
    corpus = {}
    for doc in documents:
        corpus[str(doc["id"])] = doc["content"]

    # Queries from test split
    queries = {}
    for i, pair in enumerate(test_data):
        queries[f"q{i}"] = pair["query"]

    # Relevant docs: query -> set of relevant document IDs
    relevant_docs = {}
    for i, pair in enumerate(test_data):
        relevant_docs[f"q{i}"] = {str(pair["document_id"])}

    print(f"  Corpus size:    {len(corpus)} documents")
    print(f"  Query count:    {len(queries)} queries")

    evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="legal-documents-baseline",
        mrr_at_k=[1, 5, 10],
        ndcg_at_k=[5, 10],
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[5, 10],
        score_functions={"cosine": cos_sim},
        main_score_function="cosine",
        show_progress_bar=True,
        batch_size=64
    )

    print("\nRunning baseline evaluation...")
    results = evaluator(model)

    prefix = "legal-documents-baseline_"

    print(f"\n{'='*60}")
    print(f"BASELINE EVALUATION - ModernBERT Legal (before fine-tuning)")
    print(f"{'='*60}")
    print(f"Corpus size:    {len(corpus)} legal documents")
    print(f"Test queries:   {len(queries)} queries")
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
    print("HIT RATE (correct document in top-k):")
    print(f"  Accuracy@1:   {results.get(f'{prefix}cosine_accuracy@1', 0):.4f}")
    print(f"  Accuracy@3:   {results.get(f'{prefix}cosine_accuracy@3', 0):.4f}")
    print(f"  Accuracy@5:   {results.get(f'{prefix}cosine_accuracy@5', 0):.4f}")
    print(f"  Accuracy@10:  {results.get(f'{prefix}cosine_accuracy@10', 0):.4f}")
    print()
    print("COVERAGE:")
    print(f"  Recall@5:     {results.get(f'{prefix}cosine_recall@5', 0):.4f}")
    print(f"  Recall@10:    {results.get(f'{prefix}cosine_recall@10', 0):.4f}")
    print(f"{'='*60}")

    serializable_results = {}
    for k, v in results.items():
        serializable_results[k] = v.item() if hasattr(v, 'item') else v

    with open(paths['baseline_results'], "w") as f:
        json.dump(serializable_results, f, indent=2)
    print(f"\nResults saved to {paths['baseline_results']}")

    run_example_queries(model, documents)

    print(f"\n{'='*60}")
    print("Baseline evaluation complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()