#!/usr/bin/env python3
"""
07_compare_search_results.py - Test search against live API

Calls the live search API with test queries to measure the actual
end-to-end search quality. Can compare results before and after
re-embedding with the fine-tuned model.
"""

import json
import os
import sys
from datetime import datetime
import requests
from config import DATA_DIR


def search_api(alb_dns, query, top_k=5):
    """Call the search API and return results."""
    # Try Java endpoint first
    java_url = f"http://{alb_dns}/api/search"
    python_url = f"http://{alb_dns}/search/records"

    payload = {"query": query, "top_k": top_k}

    try:
        response = requests.post(java_url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json(), "java"
    except:
        pass

    # Fall back to Python endpoint
    try:
        response = requests.post(python_url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json(), "python"
    except Exception as e:
        return None, f"error: {e}"

    return None, "error"


def main():
    # Get ALB DNS
    alb_dns = os.getenv("ALB_DNS", "llm-alb-1402483560.us-east-1.elb.amazonaws.com")

    print(f"Testing search API at: {alb_dns}")
    print()

    # Test queries
    test_queries = [
        "gift for someone who loves cooking",
        "comfortable running shoes for men",
        "budget friendly electronics for kids",
        "waterproof jacket for hiking in rain",
        "wireless noise cancelling headphones",
        "eco friendly reusable products for home",
        "back support cushion for office chair",
        "portable charger for camping trip",
        "toys for toddlers learning to walk",
        "professional camera for beginners",
    ]

    results = []
    all_top1_sims = []
    all_top5_sims = []

    print("="*70)
    print("LIVE SEARCH RESULTS")
    print("="*70)

    for query in test_queries:
        api_result, endpoint = search_api(alb_dns, query)

        if api_result is None:
            print(f'\nQuery: "{query}"')
            print(f"  ERROR: {endpoint}")
            continue

        # Parse results - handle different response formats
        if "results" in api_result:
            items = api_result["results"]
        elif "records" in api_result:
            items = api_result["records"]
        else:
            items = []

        query_result = {
            "query": query,
            "endpoint": endpoint,
            "results": []
        }

        print(f'\nQuery: "{query}"')
        print("-"*70)
        print(f"{'#':<4} | {'Product Title':<45} | {'Similarity':>10}")
        print("-"*70)

        for i, item in enumerate(items[:5], 1):
            title = item.get("title", item.get("name", "Unknown"))[:45]
            similarity = item.get("similarity", item.get("score", 0))

            if hasattr(similarity, 'item'):
                similarity = similarity.item()

            print(f"{i:<4} | {title:<45} | {similarity:>10.3f}")

            query_result["results"].append({
                "title": title,
                "similarity": similarity
            })

            if i == 1:
                all_top1_sims.append(similarity)
            all_top5_sims.append(similarity)

        print("-"*70)
        results.append(query_result)

    # Calculate aggregate stats
    if all_top1_sims:
        avg_top1 = sum(all_top1_sims) / len(all_top1_sims)
        avg_top5 = sum(all_top5_sims) / len(all_top5_sims)
        high_confidence = sum(1 for s in all_top1_sims if s > 0.5)

        print("\n" + "="*70)
        print("AGGREGATE STATISTICS")
        print("="*70)
        print(f"Average top-1 similarity:        {avg_top1:.4f}")
        print(f"Average top-5 similarity:        {avg_top5:.4f}")
        print(f"Queries with top-1 sim > 0.5:    {high_confidence}/{len(all_top1_sims)}")
        print("="*70)

    # Save results with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "alb_dns": alb_dns,
        "queries": results,
        "stats": {
            "avg_top1_similarity": avg_top1 if all_top1_sims else 0,
            "avg_top5_similarity": avg_top5 if all_top5_sims else 0,
            "high_confidence_queries": high_confidence if all_top1_sims else 0
        }
    }

    output_path = os.path.join(DATA_DIR, "live_search_results.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Check for BEFORE results to compare
    before_path = os.path.join(DATA_DIR, "live_search_results_BEFORE.json")
    if os.path.exists(before_path):
        with open(before_path, "r") as f:
            before_data = json.load(f)

        before_avg = before_data.get("stats", {}).get("avg_top1_similarity", 0)
        after_avg = output["stats"]["avg_top1_similarity"]
        improvement = after_avg - before_avg
        pct = (improvement / before_avg * 100) if before_avg > 0 else 0

        print("\n" + "="*70)
        print("BEFORE vs AFTER COMPARISON")
        print("="*70)
        print(f"BEFORE re-embedding: avg top-1 similarity = {before_avg:.4f}")
        print(f"AFTER re-embedding:  avg top-1 similarity = {after_avg:.4f}")
        print(f"Improvement: {improvement:+.4f} ({pct:+.1f}%)")
        print("="*70)
    else:
        print("\n" + "-"*70)
        print("TIP: To compare BEFORE and AFTER re-embedding:")
        print("  1. Run this script BEFORE running 06_re_embed_products.py")
        print("  2. Save the output:")
        print(f"     cp {output_path} {before_path}")
        print("  3. Run 06_re_embed_products.py to update embeddings")
        print("  4. Run this script again to see the comparison")
        print("-"*70)


if __name__ == "__main__":
    main()