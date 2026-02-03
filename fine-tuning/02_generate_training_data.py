#!/usr/bin/env python3
"""
02_generate_training_data.py - Generate synthetic training data

This script generates search queries for products. It can use either:
1. Claude API (USE_CLAUDE=True) - generates high-quality diverse queries using ANTHROPIC_API_KEY
2. Rule-based generation (USE_CLAUDE=False) - generates queries from product attributes programmatically

Set USE_CLAUDE in config.py to control which mode to use.
The rule-based approach is faster and free, suitable for demonstration.
For production fine-tuning, use the Claude API for better query diversity.
"""

import json
import os
import random
import re
import sys
import time
from config import QUERIES_PER_PRODUCT, USE_CLAUDE, ANTHROPIC_API_KEY
from version_config import (
    get_versioned_paths, get_current_version, detect_or_create_version
)

# System prompt for query generation (used with Claude API)
SYSTEM_PROMPT = "You generate realistic Amazon search queries. Return ONLY the queries, one per line, no numbering, no extra text."

# User prompt template
USER_PROMPT_TEMPLATE = """Given this Amazon product, generate {num_queries} different search queries a real customer might type when looking for this product.

Product Title: {title}
Description: {description}
Category: {category}

Requirements:
- Each query should be 3-8 words, like real search box input
- Include variety: one specific query with brand/feature details, one general need-based query, one natural language query ("something for..."), one attribute-focused query
- Do NOT copy the product title verbatim
- Think about what PROBLEM the customer is solving, not just what the product IS"""


def generate_queries_rule_based(product):
    """Generate queries using rule-based approach from product attributes."""
    queries = []
    title = product.get("title", "")
    description = product.get("description", "")
    category = product.get("category", "")

    # Extract key words from title
    title_words = re.findall(r'\b[A-Za-z]+\b', title.lower())
    title_words = [w for w in title_words if len(w) > 3 and w not in
                   {'with', 'from', 'this', 'that', 'have', 'will', 'been', 'their', 'more', 'when', 'about'}]

    # Extract brand (usually first word in title)
    brand_match = re.match(r'^([A-Za-z]+(?:\s+[A-Za-z]+)?)', title)
    brand = brand_match.group(1).lower() if brand_match else ""

    # Extract potential product type
    product_types = ["shoe", "shoes", "sneaker", "sneakers", "boot", "boots",
                     "shirt", "jacket", "pants", "dress", "watch", "bag",
                     "headphones", "speaker", "camera", "phone", "tablet",
                     "knife", "cookware", "pan", "pot", "tool", "drill",
                     "toy", "game", "book", "charger", "cable", "adapter"]

    found_type = ""
    for pt in product_types:
        if pt in title.lower():
            found_type = pt
            break

    # Extract key adjectives from description
    adjectives = ["comfortable", "lightweight", "durable", "waterproof", "wireless",
                  "portable", "premium", "professional", "compact", "powerful",
                  "soft", "sturdy", "flexible", "ergonomic", "breathable"]
    found_adj = [adj for adj in adjectives if adj in description.lower()]

    # Generate diverse query types
    # 1. Specific query with brand/features
    if brand and found_type:
        queries.append(f"{brand} {found_type}")
    elif title_words[:3]:
        queries.append(" ".join(title_words[:3]))

    # 2. General need-based query
    need_templates = [
        f"best {found_type}" if found_type else f"best {category.lower().split(',')[0]}",
        f"top rated {found_type}" if found_type else "highly reviewed products",
        f"{found_type} for everyday use" if found_type else "daily use item",
    ]
    queries.append(random.choice(need_templates))

    # 3. Natural language query
    natural_templates = [
        f"something for {random.choice(['running', 'walking', 'exercise', 'work', 'home', 'travel'])}",
        f"looking for {found_type}" if found_type else "need recommendations",
        f"gift idea {found_type}" if found_type else "gift suggestions",
    ]
    queries.append(random.choice(natural_templates))

    # 4. Attribute-focused query
    if found_adj:
        queries.append(f"{random.choice(found_adj)} {found_type}" if found_type else random.choice(found_adj) + " product")
    else:
        queries.append(f"quality {found_type}" if found_type else "high quality item")

    # Ensure we have QUERIES_PER_PRODUCT queries
    while len(queries) < QUERIES_PER_PRODUCT:
        extra = f"{random.choice(title_words) if title_words else 'product'} {random.choice(['online', 'buy', 'shop', 'deal'])}"
        queries.append(extra)

    return queries[:QUERIES_PER_PRODUCT]


def generate_queries_with_api(client, product, max_retries=3):
    """Generate search queries using Claude API."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        num_queries=QUERIES_PER_PRODUCT,
        title=product["title"],
        description=product["description"][:500],
        category=product["category"]
    )

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )

            text = response.content[0].text.strip()
            queries = [q.strip() for q in text.split("\n") if q.strip()]
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            return queries, input_tokens, output_tokens

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"  WARNING: Failed to generate queries for product {product['id']}: {e}")
                return None, 0, 0


def main():
    # Get versioned paths (continue existing version or error if none)
    version = get_current_version()
    if version is None:
        # Try to detect an existing incomplete version
        version = detect_or_create_version()

    paths = get_versioned_paths(version)
    print(f"\n{'='*60}")
    print(f"TRAINING DATA GENERATION (v{version})")
    print(f"{'='*60}")

    # Check USE_CLAUDE flag from config
    use_api = USE_CLAUDE

    if use_api:
        if not ANTHROPIC_API_KEY:
            print("ERROR: USE_CLAUDE is True but ANTHROPIC_API_KEY is not set in config.py")
            sys.exit(1)
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        print("Using Claude API for query generation (high-quality diverse queries)")
    else:
        print("USE_CLAUDE=False - using rule-based programmatic query generation")
        print("(Set USE_CLAUDE=True in config.py to use Claude API for better quality)")
        client = None

    # Load products from versioned path
    products_path = paths['products']
    if not products_path.exists():
        print(f"ERROR: Products file not found at {products_path}")
        print("Please run 01_extract_products.py first.")
        sys.exit(1)

    with open(products_path, "r") as f:
        products = json.load(f)

    print(f"\nLoaded {len(products)} products from {products_path}")
    print(f"Generating {QUERIES_PER_PRODUCT} queries per product...")
    print()

    # Generate training pairs
    all_pairs = []
    total_input_tokens = 0
    total_output_tokens = 0
    skipped_products = 0

    for i, product in enumerate(products):
        if use_api:
            queries, input_tokens, output_tokens = generate_queries_with_api(client, product)
            if queries:
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
            else:
                skipped_products += 1
                continue
        else:
            queries = generate_queries_rule_based(product)

        # Create training pairs
        for query in queries:
            pair = {
                "query": query,
                "positive": product["searchable_content"],
                "product_id": product["id"],
                "title": product["title"]
            }
            all_pairs.append(pair)

        # Progress update every 100 products
        if (i + 1) % 100 == 0 or i == len(products) - 1:
            print(f"Generated queries for {i + 1}/{len(products)} products ({len(all_pairs)} pairs so far)")

        # Rate limiting for API
        if use_api and (i + 1) % 10 == 0:
            time.sleep(0.5)

    print()

    # Save all pairs to versioned path
    with open(paths['training_pairs'], "w") as f:
        json.dump(all_pairs, f, indent=2)
    print(f"Saved all {len(all_pairs)} pairs to {paths['training_pairs']}")

    # Split into train/test (80/20)
    random.seed(42)
    shuffled_pairs = all_pairs.copy()
    random.shuffle(shuffled_pairs)

    split_idx = int(len(shuffled_pairs) * 0.8)
    train_pairs = shuffled_pairs[:split_idx]
    test_pairs = shuffled_pairs[split_idx:]

    with open(paths['train_split'], "w") as f:
        json.dump(train_pairs, f, indent=2)
    print(f"Saved {len(train_pairs)} training pairs to {paths['train_split']}")

    with open(paths['test_split'], "w") as f:
        json.dump(test_pairs, f, indent=2)
    print(f"Saved {len(test_pairs)} test pairs to {paths['test_split']}")

    # Print summary
    print()
    print("="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Total training pairs generated: {len(all_pairs)}")
    print(f"Train split size:               {len(train_pairs)}")
    print(f"Test split size:                {len(test_pairs)}")

    if use_api:
        print(f"Products skipped (errors):      {skipped_products}")
        input_cost = (total_input_tokens / 1_000_000) * 3
        output_cost = (total_output_tokens / 1_000_000) * 15
        total_cost = input_cost + output_cost
        print()
        print(f"API Token Usage:")
        print(f"  Input tokens:  {total_input_tokens:,}")
        print(f"  Output tokens: {total_output_tokens:,}")
        print(f"  Estimated cost: ${total_cost:.2f}")

    print()

    # Show sample pairs
    print("-"*60)
    print("SAMPLE TRAINING PAIRS (5 examples)")
    print("-"*60)
    sample_pairs = random.sample(all_pairs, min(5, len(all_pairs)))
    for pair in sample_pairs:
        print(f"Query:   '{pair['query']}'")
        print(f"Product: '{pair['positive'][:80]}...'")
        print()

    print("="*60)
    print("Training data generation complete!")
    print("="*60)


if __name__ == "__main__":
    main()