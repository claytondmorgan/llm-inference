#!/usr/bin/env python3
"""
06_re_embed_legal_docs.py - Re-embed all legal documents with the fine-tuned model

Updates all three embedding columns (title, content, headnote) in the legal_documents
table using the fine-tuned ModernBERT model. Connects via AWS Secrets Manager.
"""

import sys
import os
import time
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.dirname(__file__))
from config import FINETUNED_MODEL_DIR, get_db_connection
from version_config import get_versioned_paths, get_current_version, detect_or_create_version


def main():
    version = get_current_version()
    if version is None:
        version = detect_or_create_version()

    paths = get_versioned_paths(version)

    # Check for fine-tuned model
    model_dir = paths['model_dir']
    if not model_dir.exists():
        # Fall back to default fine-tuned model directory
        model_dir_str = FINETUNED_MODEL_DIR
        if not os.path.exists(model_dir_str):
            print(f"ERROR: Fine-tuned model not found at {model_dir} or {model_dir_str}")
            print("Please run 04_fine_tune.py first.")
            sys.exit(1)
    else:
        model_dir_str = str(model_dir)

    # Safety confirmation
    print("="*70)
    print("WARNING: This will overwrite all legal document embeddings in the database.")
    print("="*70)
    print()
    print("This updates ALL THREE embedding columns in legal_documents:")
    print("  - title_embedding (768-dim)")
    print("  - content_embedding (768-dim)")
    print("  - headnote_embedding (768-dim)")
    print()
    print("The /legal/search endpoint will immediately use the new embeddings.")
    print()
    confirmation = input("Type 'yes' to proceed: ")

    if confirmation.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    # Load fine-tuned model
    print(f"\nLoading fine-tuned model from {model_dir_str}...")
    model = SentenceTransformer(model_dir_str)
    print("Model loaded!")

    # Connect to database via AWS Secrets Manager
    print("\nConnecting to PostgreSQL via AWS Secrets Manager...")
    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        print("Make sure AWS credentials are configured and DB_SECRET_NAME is correct.")
        sys.exit(1)

    cursor = conn.cursor()
    print("Connected!")

    # Fetch all legal documents
    print("\nFetching legal documents to re-embed...")
    cursor.execute("""
        SELECT id, title, content, headnotes
        FROM legal_documents
        ORDER BY id
    """)
    records = cursor.fetchall()
    print(f"Found {len(records)} legal documents to re-embed")

    # Process in batches
    batch_size = 32
    total_updated = 0
    start_time = time.time()

    print(f"\nRe-embedding in batches of {batch_size}...")

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        ids = [r[0] for r in batch]
        titles = [r[1] or "" for r in batch]
        contents = [r[2] or "" for r in batch]
        headnotes = [r[3] or "" for r in batch]

        # Generate all three embeddings with normalization (matching app.py)
        title_embeddings = model.encode(titles, normalize_embeddings=True)
        content_embeddings = model.encode(contents, normalize_embeddings=True)
        headnote_embeddings = model.encode(headnotes, normalize_embeddings=True)

        # Update each record
        for j, record_id in enumerate(ids):
            title_emb_list = title_embeddings[j].tolist()
            content_emb_list = content_embeddings[j].tolist()
            headnote_emb_list = headnote_embeddings[j].tolist()

            cursor.execute("""
                UPDATE legal_documents
                SET title_embedding = %s::vector,
                    content_embedding = %s::vector,
                    headnote_embedding = %s::vector
                WHERE id = %s
            """, (title_emb_list, content_emb_list, headnote_emb_list, record_id))

        conn.commit()
        total_updated += len(batch)

        pct = (total_updated / len(records)) * 100
        print(f"  Re-embedded batch {total_updated}/{len(records)} ({pct:.1f}%)")

    elapsed = time.time() - start_time

    # Verification
    print("\nVerifying embeddings were written correctly...")
    first_id = records[0][0]
    cursor.execute("""
        SELECT id, title,
               1 - (content_embedding <=> content_embedding) as self_similarity,
               array_length(string_to_array(content_embedding::text, ','), 1) as dim
        FROM legal_documents
        WHERE id = %s
    """, (first_id,))

    verify_result = cursor.fetchone()
    print(f"Verification: Record {verify_result[0]} self-similarity = {verify_result[2]:.6f}")

    if abs(verify_result[2] - 1.0) < 0.0001:
        print("Verification PASSED!")
    else:
        print("WARNING: Self-similarity is not 1.0 - embeddings may not have been written correctly")

    cursor.close()
    conn.close()

    print(f"\n{'='*70}")
    print("RE-EMBEDDING COMPLETE")
    print(f"{'='*70}")
    print(f"Documents updated:   {total_updated}")
    print(f"Embeddings updated:  title, content, headnote (768-dim each)")
    print(f"Time elapsed:        {elapsed:.1f} seconds")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()