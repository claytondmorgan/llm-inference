#!/usr/bin/env python3
"""
02_generate_training_data.py - Generate legal research query training data

Generates synthetic (query, document) pairs for fine-tuning the legal embedding model.
Each legal document gets 10 diverse research queries that a legal professional might use.
"""

import json
import os
import sys
import re
import random
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import config
from version_config import detect_or_create_version, get_versioned_paths

random.seed(42)

# Legal stopwords to filter from keyword extraction
LEGAL_STOPWORDS = {
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "shall", "may", "can", "could", "would", "should", "must", "that",
    "this", "these", "those", "it", "its", "by", "with", "from", "at", "on",
    "as", "not", "no", "nor", "but", "if", "than", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "over", "such",
    "any", "each", "every", "all", "both", "either", "neither", "other",
    "which", "who", "whom", "whose", "what", "when", "where", "how", "why",
    "upon", "within", "without", "against", "among", "whether", "also",
    "herein", "thereof", "therein", "hereby", "wherein", "therefore",
}

# Legal concepts to detect in content for query generation
LEGAL_CONCEPTS = {
    "employment": [
        "hostile work environment", "disparate treatment", "disparate impact",
        "reasonable accommodation", "undue hardship", "constructive discharge",
        "wrongful termination", "retaliation", "quid pro quo", "harassment",
        "prima facie case", "burden of proof", "adverse employment action",
        "protected class", "bona fide occupational qualification",
    ],
    "constitutional_law": [
        "due process", "equal protection", "judicial review", "strict scrutiny",
        "rational basis", "intermediate scrutiny", "state action",
        "fundamental right", "substantive due process", "procedural due process",
    ],
    "criminal": [
        "exclusionary rule", "miranda rights", "probable cause",
        "reasonable suspicion", "search and seizure", "self-incrimination",
        "right to counsel", "fruit of the poisonous tree", "terry stop",
    ],
}


def extract_key_phrases(text, max_phrases=5):
    """Extract key legal phrases from text."""
    found = []
    text_lower = text.lower()
    for area_concepts in LEGAL_CONCEPTS.values():
        for concept in area_concepts:
            if concept in text_lower and concept not in found:
                found.append(concept)
    return found[:max_phrases]


def extract_keywords(text, max_words=6):
    """Extract meaningful keywords from text, filtering stopwords."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
    keywords = [w.lower() for w in words if w.lower() not in LEGAL_STOPWORDS]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_words]


def generate_queries_rule_based(document):
    """Generate legal research queries from document attributes."""
    queries = []
    doc_type = document.get("doc_type", "")
    title = document.get("title", "")
    content = document.get("content", "")
    headnotes = document.get("headnotes", "")
    practice_area = document.get("practice_area", "").replace("_", " ")
    jurisdiction = document.get("jurisdiction", "").replace("_", " ")

    # Extract concepts and keywords
    concepts = extract_key_phrases(content + " " + headnotes)
    title_keywords = extract_keywords(title, 4)
    content_keywords = extract_keywords(content, 8)
    headnote_keywords = extract_keywords(headnotes, 6) if headnotes else title_keywords

    # --- Query templates by doc_type ---

    if doc_type == "case_law":
        # 1. Issue-based query from concepts
        if concepts:
            queries.append(f"{concepts[0]} legal standard")
        # 2. Elements query
        if practice_area:
            queries.append(f"elements of {practice_area} claim")
        # 3. Jurisdiction + topic
        if jurisdiction and practice_area:
            queries.append(f"{jurisdiction} {practice_area} case law")
        # 4. What constitutes query
        if concepts:
            queries.append(f"what constitutes {concepts[0]}")
        # 5. Standard of review
        if headnote_keywords:
            queries.append(f"{' '.join(headnote_keywords[:3])} standard of review")
        # 6. Natural language research question
        if concepts:
            queries.append(f"when can an employee prove {concepts[0]}")
        # 7. Partial title lookup
        if title_keywords:
            queries.append(f"{' '.join(title_keywords[:2])} ruling")
        # 8. Keyword combination
        if content_keywords:
            queries.append(f"{' '.join(content_keywords[:3])}")
        # 9. Burden of proof query
        if practice_area:
            queries.append(f"burden of proof {practice_area}")
        # 10. Landmark case query
        if len(concepts) > 1:
            queries.append(f"{concepts[1]} case holding")
        elif practice_area:
            queries.append(f"leading {practice_area} precedent")

    elif doc_type == "statute":
        # 1. Statutory requirements
        if title_keywords:
            queries.append(f"{' '.join(title_keywords[:3])} requirements")
        # 2. Protected classes
        if practice_area:
            queries.append(f"protected classes under {practice_area} statute")
        # 3. Employer obligations
        queries.append(f"employer obligations {practice_area}")
        # 4. Definition query
        if content_keywords:
            queries.append(f"definition of {content_keywords[0]} under federal law")
        # 5. Penalty/enforcement
        queries.append(f"{practice_area} statutory penalties")
        # 6. Scope of coverage
        if title_keywords:
            queries.append(f"who is covered by {' '.join(title_keywords[:2])}")
        # 7. Exemptions
        queries.append(f"{practice_area} statutory exemptions")
        # 8. Filing requirements
        queries.append(f"how to file {practice_area} complaint")
        # 9. Natural language
        if concepts:
            queries.append(f"what does the law say about {concepts[0]}")
        else:
            queries.append(f"federal {practice_area} law overview")
        # 10. Keyword combination
        if headnote_keywords:
            queries.append(f"{' '.join(headnote_keywords[:3])}")
        else:
            queries.append(f"{practice_area} legal framework")

    elif doc_type == "practice_guide":
        # 1. How-to procedural
        if title_keywords:
            queries.append(f"how to {' '.join(title_keywords[:3])}")
        # 2. Checklist
        queries.append(f"{practice_area} compliance checklist")
        # 3. Best practices
        queries.append(f"{practice_area} best practices for employers")
        # 4. Step by step
        if concepts:
            queries.append(f"steps for handling {concepts[0]}")
        else:
            queries.append(f"steps for {practice_area} compliance")
        # 5. Common mistakes
        queries.append(f"common mistakes in {practice_area} cases")
        # 6. Documentation
        queries.append(f"documentation requirements {practice_area}")
        # 7. Natural language
        queries.append(f"what should employer do about {practice_area}")
        # 8. Timeline
        queries.append(f"deadlines and timelines {practice_area}")
        # 9. Keyword combo
        if content_keywords:
            queries.append(f"{' '.join(content_keywords[:3])}")
        else:
            queries.append(f"{practice_area} practical guidance")
        # 10. Prevention
        queries.append(f"preventing {practice_area} liability")

    elif doc_type == "regulation":
        # 1. Regulatory requirements
        if title_keywords:
            queries.append(f"{' '.join(title_keywords[:3])} regulatory requirements")
        # 2. Compliance standards
        queries.append(f"{practice_area} regulatory compliance")
        # 3. Enforcement procedures
        queries.append(f"{practice_area} enforcement procedures")
        # 4. Agency guidance
        queries.append(f"agency guidance on {practice_area}")
        # 5. Definitions
        if content_keywords:
            queries.append(f"regulatory definition of {content_keywords[0]}")
        else:
            queries.append(f"{practice_area} regulatory definitions")
        # 6. Obligations
        queries.append(f"employer regulatory obligations {practice_area}")
        # 7. Standards
        if concepts:
            queries.append(f"standard for {concepts[0]}")
        else:
            queries.append(f"{practice_area} regulatory standard")
        # 8. Natural language
        queries.append(f"what regulations apply to {practice_area}")
        # 9. Keyword combo
        if headnote_keywords:
            queries.append(f"{' '.join(headnote_keywords[:3])}")
        else:
            queries.append(f"{practice_area} regulatory framework")
        # 10. Scope
        queries.append(f"scope of {practice_area} regulations")

    # Ensure we have exactly QUERIES_PER_DOCUMENT queries
    # Pad with keyword-based queries if needed
    while len(queries) < config.QUERIES_PER_DOCUMENT:
        if content_keywords:
            sample_size = min(3, len(content_keywords))
            kw_sample = random.sample(content_keywords, sample_size)
            queries.append(" ".join(kw_sample))
        else:
            queries.append(f"{practice_area} legal research")

    return queries[:config.QUERIES_PER_DOCUMENT]


def generate_queries_with_api(document, num_queries=10):
    """Generate legal queries using Claude API."""
    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed. Falling back to rule-based.")
        return generate_queries_rule_based(document)

    if not config.ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set. Falling back to rule-based.")
        return generate_queries_rule_based(document)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    content_excerpt = document["content"][:500]
    headnotes = document.get("headnotes", "")[:300]

    prompt = f"""Generate {num_queries} different search queries a legal professional might use when researching this topic.

Document Type: {document['doc_type']}
Title: {document['title']}
Practice Area: {document.get('practice_area', '')}
Jurisdiction: {document.get('jurisdiction', '')}
Headnotes: {headnotes}
Content (excerpt): {content_excerpt}

Requirements:
- Each query should be 3-10 words
- Include variety: issue-based, standard-of-review, procedural, natural language
- Think about what LEGAL QUESTION the researcher is trying to answer
- Include both broad topical queries and specific legal standard queries
- Do NOT include the full case name or citation verbatim

Return ONLY the queries, one per line, no numbering."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        queries = [q.strip() for q in text.split("\n") if q.strip()]
        return queries[:num_queries]
    except Exception as e:
        print(f"  API error: {e}, falling back to rule-based")
        return generate_queries_rule_based(document)


def generate_training_data():
    """Generate training data from extracted legal documents."""
    print("=" * 60)
    print("Step 2: Generate Legal Research Training Data")
    print("=" * 60)

    version = detect_or_create_version()
    paths = get_versioned_paths(version)

    # Load documents
    if not paths['documents'].exists():
        print("ERROR: documents.json not found. Run 01_extract_legal_docs.py first.")
        sys.exit(1)

    with open(paths['documents'], 'r') as f:
        documents = json.load(f)

    print(f"\nLoaded {len(documents)} legal documents")
    print(f"Generating {config.QUERIES_PER_DOCUMENT} queries per document...")
    print(f"Mode: {'Claude API' if config.USE_CLAUDE else 'Rule-based'}")
    print()

    all_pairs = []
    generate_fn = generate_queries_with_api if config.USE_CLAUDE else generate_queries_rule_based

    for i, doc in enumerate(documents):
        queries = generate_fn(doc)

        for query in queries:
            pair = {
                "query": query,
                "positive": doc["content"],
                "document_id": doc["id"],
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "doc_type": doc["doc_type"],
                "practice_area": doc.get("practice_area", ""),
            }
            all_pairs.append(pair)

        if (i + 1) % 10 == 0 or i == len(documents) - 1:
            print(f"  Processed {i + 1}/{len(documents)} documents ({len(all_pairs)} pairs)")

    # Save all pairs
    with open(paths['training_pairs'], 'w') as f:
        json.dump(all_pairs, f, indent=2)

    # Split 80/20
    random.shuffle(all_pairs)
    split_idx = int(len(all_pairs) * 0.8)
    train_split = all_pairs[:split_idx]
    test_split = all_pairs[split_idx:]

    with open(paths['train_split'], 'w') as f:
        json.dump(train_split, f, indent=2)
    with open(paths['test_split'], 'w') as f:
        json.dump(test_split, f, indent=2)

    # Summary
    print(f"\nTotal pairs generated: {len(all_pairs)}")
    print(f"Training split: {len(train_split)} ({len(train_split)/len(all_pairs)*100:.0f}%)")
    print(f"Test split: {len(test_split)} ({len(test_split)/len(all_pairs)*100:.0f}%)")

    # Show sample queries
    print(f"\nSample queries:")
    for pair in all_pairs[:5]:
        print(f"  [{pair['doc_type']}] {pair['query']}")
        print(f"    -> {pair['title'][:60]}")

    type_counts = Counter(p["doc_type"] for p in all_pairs)
    print(f"\nPairs by document type:")
    for dtype, count in type_counts.most_common():
        print(f"  {dtype}: {count}")

    return all_pairs


if __name__ == "__main__":
    generate_training_data()