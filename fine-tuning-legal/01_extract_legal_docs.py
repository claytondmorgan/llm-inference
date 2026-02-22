#!/usr/bin/env python3
"""
01_extract_legal_docs.py - Extract legal documents from CSV

Reads legal-documents.csv and creates a structured JSON file for fine-tuning.
"""

import csv
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import config
from version_config import initialize_new_version, get_versioned_paths, create_version_readme, get_config_snapshot


def create_searchable_content(row):
    """Create searchable content combining legal document fields."""
    parts = []
    if row.get("title"):
        parts.append(f"Title: {row['title']}")
    if row.get("citation"):
        parts.append(f"Citation: {row['citation']}")
    if row.get("court"):
        parts.append(f"Court: {row['court']}")
    if row.get("practice_area"):
        parts.append(f"Practice Area: {row['practice_area']}")
    if row.get("content"):
        parts.append(f"Content: {row['content']}")
    if row.get("headnotes"):
        parts.append(f"Headnotes: {row['headnotes']}")
    return " | ".join(parts)


def extract_documents():
    """Extract legal documents from CSV."""
    print("=" * 60)
    print("Step 1: Extract Legal Documents")
    print("=" * 60)

    # Initialize versioning
    version = initialize_new_version()
    paths = get_versioned_paths(version)

    # Read CSV
    csv_path = config.CSV_PATH
    if not os.path.exists(csv_path):
        print(f"ERROR: {csv_path} not found")
        print("Run generate_legal_data.py first to create the CSV.")
        sys.exit(1)

    print(f"\nReading: {csv_path}")

    documents = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            searchable_content = create_searchable_content(row)
            doc = {
                "id": idx + 1,
                "doc_id": row["doc_id"],
                "doc_type": row["doc_type"],
                "title": row["title"],
                "citation": row.get("citation", ""),
                "jurisdiction": row.get("jurisdiction", ""),
                "court": row.get("court", ""),
                "content": row["content"],
                "headnotes": row.get("headnotes", ""),
                "practice_area": row.get("practice_area", ""),
                "status": row.get("status", "good_law"),
                "searchable_content": searchable_content,
                "source_file": "legal-documents.csv"
            }
            documents.append(doc)

    # Save
    with open(paths['documents'], 'w') as f:
        json.dump(documents, f, indent=2)

    # Summary
    type_counts = Counter(d["doc_type"] for d in documents)
    area_counts = Counter(d["practice_area"] for d in documents)
    status_counts = Counter(d["status"] for d in documents)
    avg_content_len = sum(len(d["content"]) for d in documents) / len(documents)

    print(f"\nExtracted {len(documents)} legal documents")
    print(f"\nBy document type:")
    for dtype, count in type_counts.most_common():
        print(f"  {dtype}: {count}")

    print(f"\nBy practice area:")
    for area, count in area_counts.most_common():
        print(f"  {area}: {count}")

    print(f"\nBy status:")
    for status, count in status_counts.most_common():
        print(f"  {status}: {count}")

    print(f"\nAverage content length: {avg_content_len:.0f} chars")
    print(f"\nSaved to: {paths['documents']}")

    # Create version README
    create_version_readme(version, get_config_snapshot())

    return documents


if __name__ == "__main__":
    extract_documents()