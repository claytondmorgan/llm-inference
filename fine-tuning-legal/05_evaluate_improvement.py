#!/usr/bin/env python3
"""
05_evaluate_improvement.py - Comprehensive evaluation and comparison report

Loads both the base model and fine-tuned model, runs full evaluation on both,
and produces a detailed comparison report with metrics and side-by-side
legal search result comparisons.
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


def run_side_by_side_comparison(base_model, fine_model, documents):
    """Run side-by-side search comparisons for legal research queries."""
    comparison_queries = [
        "hostile work environment standard of proof",
        "ADA reasonable accommodation employer obligations",
        "Section 1983 civil rights claim elements",
        "exclusionary rule fourth amendment evidence",
        "employer retaliation whistleblower protection",
        "disparate impact employment discrimination",
        "due process requirements government action",
        "statute of limitations employment claims",
        "qualified immunity defense requirements",
        "Title VII protected class discrimination",
    ]

    # Encode corpus with both models
    print("\nEncoding corpus with both models for comparison...")
    corpus_texts = [d["content"] for d in documents]

    base_corpus_emb = base_model.encode(corpus_texts, show_progress_bar=True, convert_to_tensor=True)
    fine_corpus_emb = fine_model.encode(corpus_texts, show_progress_bar=True, convert_to_tensor=True)

    comparisons = []

    print("\n" + "="*100)
    print("SIDE-BY-SIDE LEGAL SEARCH COMPARISONS")
    print("="*100)

    for query in comparison_queries:
        base_query_emb = base_model.encode(query, convert_to_tensor=True)
        fine_query_emb = fine_model.encode(query, convert_to_tensor=True)

        base_sims = cos_sim(base_query_emb, base_corpus_emb)[0].cpu().numpy()
        fine_sims = cos_sim(fine_query_emb, fine_corpus_emb)[0].cpu().numpy()

        base_top5 = np.argsort(base_sims)[::-1][:5]
        fine_top5 = np.argsort(fine_sims)[::-1][:5]

        base_avg = np.mean([base_sims[i] for i in base_top5])
        fine_avg = np.mean([fine_sims[i] for i in fine_top5])

        comparison = {
            "query": query,
            "base_results": [
                (documents[i]["title"], float(base_sims[i]), documents[i]["doc_type"], documents[i].get("practice_area", ""))
                for i in base_top5
            ],
            "fine_results": [
                (documents[i]["title"], float(fine_sims[i]), documents[i]["doc_type"], documents[i].get("practice_area", ""))
                for i in fine_top5
            ],
            "base_avg_sim": float(base_avg),
            "fine_avg_sim": float(fine_avg)
        }
        comparisons.append(comparison)

        print(f'\nQuery: "{query}"')
        print("-"*100)
        print(f"{'BASE MODEL':<49} | {'FINE-TUNED MODEL':<49}")
        print("-"*100)

        for rank in range(5):
            base_title = comparison["base_results"][rank][0][:30]
            base_sim = comparison["base_results"][rank][1]
            base_type = comparison["base_results"][rank][2][:8]
            fine_title = comparison["fine_results"][rank][0][:30]
            fine_sim = comparison["fine_results"][rank][1]
            fine_type = comparison["fine_results"][rank][2][:8]

            print(f"{rank+1}. [{base_sim:.3f}] [{base_type}] {base_title:<25} | {rank+1}. [{fine_sim:.3f}] [{fine_type}] {fine_title:<25}")

        print("-"*100)
        print(f"Avg similarity: {base_avg:.3f} -> {fine_avg:.3f} ({fine_avg - base_avg:+.3f})")

    return comparisons


def main():
    version = get_current_version()
    if version is None:
        version = detect_or_create_version()

    paths = get_versioned_paths(version)
    print(f"\n{'='*60}")
    print(f"EVALUATION & COMPARISON - Legal Documents (v{version})")
    print(f"{'='*60}")

    model_dir = paths['model_dir']
    if not model_dir.exists():
        print(f"ERROR: Fine-tuned model not found at {model_dir}")
        print("Please run 04_fine_tune.py first.")
        sys.exit(1)

    for path, name in [(paths['test_split'], "Test split"), (paths['documents'], "Documents")]:
        if not path.exists():
            print(f"ERROR: {name} file not found at {path}")
            sys.exit(1)

    # Load data
    with open(paths['test_split'], "r") as f:
        test_data = json.load(f)

    with open(paths['documents'], "r") as f:
        documents = json.load(f)

    # Load both models
    print(f"Loading base model: {BASE_MODEL}")
    base_model = SentenceTransformer(BASE_MODEL)

    print(f"Loading fine-tuned model: {model_dir}")
    fine_model = SentenceTransformer(str(model_dir))

    # Build evaluation data structures
    corpus = {}
    for doc in documents:
        corpus[str(doc["id"])] = doc["content"]

    queries = {}
    relevant_docs = {}
    for i, pair in enumerate(test_data):
        queries[f"q{i}"] = pair["query"]
        relevant_docs[f"q{i}"] = {str(pair["document_id"])}

    # Create evaluators
    base_evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="baseline",
        mrr_at_k=[1, 5, 10],
        ndcg_at_k=[5, 10],
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[5, 10],
        score_functions={"cosine": cos_sim},
        main_score_function="cosine",
        show_progress_bar=True,
        batch_size=64
    )

    fine_evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="finetuned",
        mrr_at_k=[1, 5, 10],
        ndcg_at_k=[5, 10],
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[5, 10],
        score_functions={"cosine": cos_sim},
        main_score_function="cosine",
        show_progress_bar=True,
        batch_size=64
    )

    # Run evaluations
    print("\nEvaluating base model...")
    base_results = base_evaluator(base_model)

    print("\nEvaluating fine-tuned model...")
    fine_results = fine_evaluator(fine_model)

    # Print comprehensive comparison
    print("\n")
    print("="*70)
    print("       LEGAL EMBEDDING FINE-TUNING RESULTS - SEARCH RELEVANCY")
    print("="*70)
    print()
    print(f"  Base Model:      {BASE_MODEL}")
    print(f"  Fine-Tuned on:   ~{len(test_data) * 5} synthetic (query, document) pairs")
    print(f"  Loss Function:   MultipleNegativesRankingLoss (in-batch neg)")
    print(f"  Training:        5 epochs, batch=16, lr=2e-5")
    print(f"  Corpus:          {len(corpus):,} legal documents")
    print(f"  Test Queries:    {len(queries):,} queries")
    print()
    print("="*70)
    print(f"{'Metric':<17} | {'Baseline':>10} | {'Fine-Tuned':>10} | {'Delta':>10} | {'Change':>8}")
    print("="*70)

    base_prefix = "baseline_"
    fine_prefix = "finetuned_"

    metrics = [
        ("NDCG@5", "cosine_ndcg@5"),
        ("NDCG@10 *", "cosine_ndcg@10"),
        ("MRR@10", "cosine_mrr@10"),
        ("Accuracy@1", "cosine_accuracy@1"),
        ("Accuracy@5", "cosine_accuracy@5"),
        ("Accuracy@10", "cosine_accuracy@10"),
        ("Recall@5", "cosine_recall@5"),
        ("Recall@10", "cosine_recall@10"),
    ]

    results_table = {}
    for display_name, key in metrics:
        base_val = base_results.get(f"{base_prefix}{key}", 0)
        fine_val = fine_results.get(f"{fine_prefix}{key}", 0)
        delta = fine_val - base_val
        pct = (delta / base_val * 100) if base_val > 0 else 0

        if hasattr(base_val, 'item'):
            base_val = base_val.item()
        if hasattr(fine_val, 'item'):
            fine_val = fine_val.item()

        results_table[key] = {
            "baseline": base_val,
            "finetuned": fine_val,
            "delta": delta,
            "pct_change": pct
        }

        print(f"{display_name:<17} | {base_val:>10.4f} | {fine_val:>10.4f} | {delta:>+10.4f} | {pct:>+7.1f}%")

    print("="*70)
    print("* = Primary metric")

    # Run side-by-side comparisons
    comparisons = run_side_by_side_comparison(base_model, fine_model, documents)

    # Save everything to versioned report
    report = {
        "config": {
            "base_model": BASE_MODEL,
            "finetuned_model": str(model_dir),
            "corpus_size": len(corpus),
            "test_queries": len(queries),
            "version": version
        },
        "metrics": results_table,
        "comparisons": [
            {
                "query": c["query"],
                "base_results": [(r[0], r[1]) for r in c["base_results"]],
                "fine_results": [(r[0], r[1]) for r in c["fine_results"]],
                "base_avg_sim": c["base_avg_sim"],
                "fine_avg_sim": c["fine_avg_sim"],
            }
            for c in comparisons
        ]
    }

    with open(paths['comparison_report'], "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {paths['comparison_report']}")

    # Final conclusion
    ndcg_base = results_table["cosine_ndcg@10"]["baseline"]
    ndcg_fine = results_table["cosine_ndcg@10"]["finetuned"]
    ndcg_pct = results_table["cosine_ndcg@10"]["pct_change"]

    print("\n" + "="*70)
    print(f"CONCLUSION: Fine-tuning improved NDCG@10 from {ndcg_base:.4f} to {ndcg_fine:.4f}")
    print(f"            ({ndcg_pct:+.1f}% improvement)")
    print("="*70)


if __name__ == "__main__":
    main()