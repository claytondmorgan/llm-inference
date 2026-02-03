#!/usr/bin/env python3
"""
01_extract_products.py - Extract products from local CSV for fine-tuning

Since the RDS database is not accessible from outside the VPC,
this script loads products from the local amazon-products.csv file
and creates the same data structure that would exist in the database.

This script initializes a new versioned run of the fine-tuning pipeline.
"""

import json
import random
import os
import pandas as pd
from version_config import (
    initialize_new_version, get_versioned_paths, create_version_readme,
    get_current_version
)

# Path to the CSV file
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "amazon-products.csv")


def create_searchable_content(row):
    """Create searchable_content field like the ingestion pipeline does."""
    parts = []

    # Title
    if pd.notna(row.get("title")):
        parts.append(f"Title: {row['title']}")

    # Brand
    if pd.notna(row.get("brand")):
        parts.append(f"Brand: {row['brand']}")

    # Description
    if pd.notna(row.get("description")):
        parts.append(f"Description: {row['description']}")

    # Categories
    if pd.notna(row.get("categories")):
        try:
            categories = eval(row["categories"]) if isinstance(row["categories"], str) else row["categories"]
            if categories:
                parts.append(f"Categories: {', '.join(categories)}")
        except:
            parts.append(f"Categories: {row['categories']}")

    # Features
    if pd.notna(row.get("features")):
        parts.append(f"Features: {row['features']}")

    return " | ".join(parts)


def extract_category(row):
    """Extract primary category from categories list."""
    if pd.notna(row.get("categories")):
        try:
            categories = eval(row["categories"]) if isinstance(row["categories"], str) else row["categories"]
            if categories and len(categories) > 0:
                return categories[0]
        except:
            pass
    return "Unknown"


def main():
    # Initialize a new version for this run
    version = initialize_new_version()
    paths = get_versioned_paths(version)

    # Ensure version directory exists
    paths['version_dir'].mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"FINE-TUNING RUN v{version}")
    print(f"{'='*60}")
    print(f"Loading products from CSV: {CSV_PATH}")

    # Load CSV
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} rows from CSV")

    # Convert to product list
    products = []
    for idx, row in df.iterrows():
        # Create searchable_content like the ingestion pipeline does
        searchable_content = create_searchable_content(row)

        # Skip if no meaningful content
        if len(searchable_content) < 50:
            continue

        product = {
            "id": idx + 1,  # Simulated database ID
            "title": str(row.get("title", "")) if pd.notna(row.get("title")) else "",
            "description": str(row.get("description", ""))[:2000] if pd.notna(row.get("description")) else "",
            "category": extract_category(row),
            "tags": [],
            "searchable_content": searchable_content,
            "source_file": "amazon-products.csv"
        }
        products.append(product)

    print(f"Processed {len(products)} valid products")

    # Save products to versioned JSON path
    products_path = paths['products']
    with open(products_path, "w") as f:
        json.dump(products, f, indent=2)
    print(f"\nSaved {len(products)} products to {products_path}")

    # Calculate summary statistics
    unique_categories = set(p["category"] for p in products if p["category"])
    avg_content_length = sum(len(p["searchable_content"]) for p in products) / len(products) if products else 0
    avg_tokens = avg_content_length / 4  # Approximate tokens

    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Total products extracted:       {len(products)}")
    print(f"Number of unique categories:    {len(unique_categories)}")
    print(f"Avg searchable_content length:  {avg_content_length:.0f} chars (~{avg_tokens:.0f} tokens)")

    # Sample 3 random products
    print("\n" + "-"*60)
    print("SAMPLE PRODUCTS (3 random)")
    print("-"*60)
    sample_products = random.sample(products, min(3, len(products)))
    for p in sample_products:
        print(f"  ID: {p['id']}")
        print(f"    Title:    {p['title'][:60]}...")
        print(f"    Category: {p['category']}")
        print()

    # Show first product's searchable_content
    if products:
        print("-"*60)
        print("FIRST PRODUCT'S SEARCHABLE_CONTENT (format reference)")
        print("-"*60)
        first_product = products[0]
        print(f"Product ID: {first_product['id']}")
        print(f"Title: {first_product['title']}")
        print(f"\nsearchable_content:")
        print("-"*40)
        print(first_product['searchable_content'][:1000])
        if len(first_product['searchable_content']) > 1000:
            print(f"... (truncated, total {len(first_product['searchable_content'])} chars)")

    # Create initial version README with config snapshot
    create_version_readme(version)

    print("\n" + "="*60)
    print(f"Extraction complete! (v{version})")
    print(f"Data stored in: {paths['version_dir']}")
    print("="*60)


if __name__ == "__main__":
    main()