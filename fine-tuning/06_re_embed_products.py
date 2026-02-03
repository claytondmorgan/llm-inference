#!/usr/bin/env python3
"""
06_re_embed_products.py - Re-embed all products with the fine-tuned model

Updates all product embeddings in PostgreSQL using the fine-tuned model.
This makes the live search API use the improved embeddings.
"""

import sys
import time
import psycopg2
from sentence_transformers import SentenceTransformer
from config import (
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS,
    FINETUNED_MODEL_DIR
)


def main():
    # Check for database password
    if not DB_PASS:
        print("ERROR: DB_PASSWORD environment variable is not set.")
        print("Please set it with: export DB_PASSWORD='your_password'")
        sys.exit(1)

    # Safety confirmation
    print("="*70)
    print("WARNING: This will overwrite all product embeddings in the database.")
    print("="*70)
    print()
    print("This will overwrite all product embeddings in the live database.")
    print("The Java and Python search services will immediately use the new embeddings.")
    print()
    confirmation = input("Type 'yes' to proceed: ")

    if confirmation.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    # Load fine-tuned model
    print(f"\nLoading fine-tuned model from {FINETUNED_MODEL_DIR}...")
    model = SentenceTransformer(FINETUNED_MODEL_DIR)
    print("Model loaded!")

    # Connect to database
    print(f"\nConnecting to PostgreSQL at {DB_HOST}...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    cursor = conn.cursor()
    print("Connected!")

    # Fetch all active records
    print("\nFetching records to re-embed...")
    cursor.execute("""
        SELECT id, title, searchable_content
        FROM ingested_records
        WHERE status = 'active'
        ORDER BY id
    """)
    records = cursor.fetchall()
    print(f"Found {len(records)} records to re-embed")

    # Process in batches
    batch_size = 64
    total_updated = 0
    start_time = time.time()

    print(f"\nRe-embedding in batches of {batch_size}...")

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        # Extract texts
        ids = [r[0] for r in batch]
        titles = [r[1] or "" for r in batch]
        contents = [r[2] or "" for r in batch]

        # Generate embeddings
        content_embeddings = model.encode(contents)
        title_embeddings = model.encode(titles)

        # Update each record
        for j, record_id in enumerate(ids):
            content_emb_list = content_embeddings[j].tolist()
            title_emb_list = title_embeddings[j].tolist()

            cursor.execute("""
                UPDATE ingested_records
                SET content_embedding = %s::vector,
                    title_embedding = %s::vector
                WHERE id = %s
            """, (content_emb_list, title_emb_list, record_id))

        conn.commit()
        total_updated += len(batch)

        # Progress update
        pct = (total_updated / len(records)) * 100
        print(f"Re-embedded batch {total_updated}/{len(records)} ({pct:.1f}%)")

    elapsed = time.time() - start_time

    # Verification query
    print("\nVerifying embeddings were written correctly...")
    first_id = records[0][0]
    cursor.execute(f"""
        SELECT id, title,
               1 - (content_embedding <=> content_embedding) as self_similarity
        FROM ingested_records
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
    print(f"Records updated: {total_updated}")
    print(f"Time elapsed:    {elapsed:.1f} seconds")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()