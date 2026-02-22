#!/usr/bin/env python3
"""
07_compare_search_results.py - Test legal search against live API

Calls the live /legal/search endpoint with test queries to measure actual
end-to-end search quality. Tests both semantic and hybrid search modes.
"""

import json
import os
import sys
from datetime import datetime
import requests

sys.path.insert(0, os.path.dirname(__file__))
from config import ALB_URL, DATA_DIR


def search_legal_api(base_url, query, search_field="content", top_k=5):
    """Call the /legal/search API endpoint."""
    url = f"{base_url}/legal/search"
    payload = {
        "query": query,
        "search_field": search_field,
        "top_k": top_k,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return {"error": str(e)}

    return {"error": f"HTTP {response.status_code}"}


def main():
    base_url = os.getenv("ALB_URL", ALB_URL)

    print(f"Testing legal search API at: {base_url}")
    print()

    # Legal research test queries
    test_queries = [
        "hostile work environment standard",
        "ADA reasonable accommodation requirements",
        "Section 1983 civil rights claim elements",
        "exclusionary rule fourth amendment",
        "employer retaliation whistleblower protection",
        "disparate impact employment discrimination",
        "due process requirements government action",
        "Title VII protected class discrimination",
        "qualified immunity defense",
        "wrongful termination constructive discharge",
    ]

    # Test both search modes
    for search_mode in ["content", "hybrid"]:
        results = []
        all_top1_sims = []
        all_top5_sims = []

        print("="*80)
        print(f"LIVE LEGAL SEARCH RESULTS - {search_mode.upper()} MODE")
        print("="*80)

        for query in test_queries:
            api_result = search_legal_api(base_url, query, search_field=search_mode)

            if "error" in api_result:
                print(f'\nQuery: "{query}"')
                print(f"  ERROR: {api_result['error']}")
                continue

            items = api_result.get("results", [])

            query_result = {
                "query": query,
                "search_field": search_mode,
                "results": []
            }

            print(f'\nQuery: "{query}"')
            print("-"*80)
            print(f"{'#':<3} | {'Title':<35} | {'Type':<12} | {'Method':<8} | {'Sim':>6}")
            print("-"*80)

            for i, item in enumerate(items[:5], 1):
                title = item.get("title", "Unknown")[:35]
                doc_type = item.get("doc_type", "")[:12]
                similarity = item.get("similarity", 0)
                search_method = item.get("search_method", search_mode)[:8]

                if hasattr(similarity, 'item'):
                    similarity = similarity.item()

                print(f"{i:<3} | {title:<35} | {doc_type:<12} | {search_method:<8} | {similarity:>6.3f}")

                query_result["results"].append({
                    "title": item.get("title", ""),
                    "doc_type": doc_type,
                    "similarity": similarity,
                    "search_method": search_method,
                })

                if i == 1:
                    all_top1_sims.append(similarity)
                all_top5_sims.append(similarity)

            print("-"*80)
            results.append(query_result)

        # Aggregate stats
        if all_top1_sims:
            avg_top1 = sum(all_top1_sims) / len(all_top1_sims)
            avg_top5 = sum(all_top5_sims) / len(all_top5_sims)
            high_confidence = sum(1 for s in all_top1_sims if s > 0.5)

            print("\n" + "="*80)
            print(f"AGGREGATE STATISTICS - {search_mode.upper()} MODE")
            print("="*80)
            print(f"Average top-1 similarity:        {avg_top1:.4f}")
            print(f"Average top-5 similarity:        {avg_top5:.4f}")
            print(f"Queries with top-1 sim > 0.5:    {high_confidence}/{len(all_top1_sims)}")
            print("="*80)

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = {
            "timestamp": timestamp,
            "alb_url": base_url,
            "search_mode": search_mode,
            "queries": results,
            "stats": {
                "avg_top1_similarity": avg_top1 if all_top1_sims else 0,
                "avg_top5_similarity": avg_top5 if all_top5_sims else 0,
                "high_confidence_queries": high_confidence if all_top1_sims else 0
            }
        }

        os.makedirs(DATA_DIR, exist_ok=True)
        output_path = os.path.join(DATA_DIR, f"live_search_results_{search_mode}.json")
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {output_path}")

        print()


if __name__ == "__main__":
    main()