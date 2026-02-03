import pandas as pd
import logging
from typing import List, Dict, Optional
from app.config import Config
from app.embeddings import EmbeddingGenerator
from app.database import DatabaseManager

logger = logging.getLogger(__name__)


class CSVProcessor:
    def __init__(self, embedder: EmbeddingGenerator, db: DatabaseManager):
        self.embedder = embedder
        self.db = db
        self.batch_size = Config.BATCH_SIZE
        self.embedding_batch_size = Config.EMBEDDING_BATCH_SIZE

    def process_file(self, file_path: str, source_file: str) -> Dict:
        """Process a CSV file in batches."""
        try:
            # Create ingestion job
            job_id = self.db.create_job(source_file)
            logger.info(f"Job {job_id}: Starting processing of {source_file}")

            # Read CSV with error handling
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding='latin-1')

            total_rows = len(df)
            logger.info(f"Job {job_id}: Read {total_rows} rows from CSV")

            # Log detected columns
            logger.info(f"Job {job_id}: CSV columns: {list(df.columns)}")

            # Detect field mappings
            field_map = self._detect_fields(df)
            logger.info(f"Job {job_id}: Field mapping: {field_map}")

            self.db.update_job(job_id, total_rows=total_rows)

            processed = 0
            failed = 0

            # Process in batches
            for batch_start in range(0, total_rows, self.batch_size):
                batch_end = min(batch_start + self.batch_size, total_rows)
                batch_df = df.iloc[batch_start:batch_end]

                try:
                    batch_count = self._process_batch(
                        batch_df, source_file, batch_start, field_map
                    )
                    processed += batch_count
                    logger.info(
                        f"Job {job_id}: Processed batch {batch_start}-{batch_end} "
                        f"({processed}/{total_rows})"
                    )
                except Exception as e:
                    logger.error(f"Job {job_id}: Batch {batch_start}-{batch_end} failed: {e}")
                    failed += len(batch_df)

                # Update progress
                self.db.update_job(job_id, processed_rows=processed, failed_rows=failed)

            # Mark job complete
            if failed == 0:
                status = 'completed'
            elif processed > 0:
                status = 'completed_with_errors'
            else:
                status = 'failed'

            self.db.update_job(job_id, status=status)

            logger.info(
                f"Job {job_id}: Finished - {processed} processed, {failed} failed"
            )

            return {
                'success': failed == 0 or processed > 0,
                'job_id': job_id,
                'total_rows': total_rows,
                'processed_rows': processed,
                'failed_rows': failed
            }

        except Exception as e:
            logger.error(f"File processing failed: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _detect_fields(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """Auto-detect which CSV columns map to which fields."""
        columns_lower = {col.lower().strip(): col for col in df.columns}

        field_map = {
            'title': None,
            'description': None,
            'category': None,
            'tags': None
        }

        # Try to match columns to fields
        for col_lower, col_original in columns_lower.items():
            if col_lower in [f.strip().lower() for f in Config.TITLE_FIELDS]:
                field_map['title'] = col_original
            elif col_lower in [f.strip().lower() for f in Config.DESCRIPTION_FIELDS]:
                field_map['description'] = col_original
            elif col_lower in [f.strip().lower() for f in Config.CATEGORY_FIELDS]:
                field_map['category'] = col_original
            elif col_lower in [f.strip().lower() for f in Config.TAG_FIELDS]:
                field_map['tags'] = col_original

        return field_map

    def _process_batch(
        self, batch_df: pd.DataFrame, source_file: str,
        start_row: int, field_map: Dict
    ) -> int:
        """Process a batch of rows."""
        records = []

        for idx, row in batch_df.iterrows():
            record = self._extract_record(row, source_file, start_row + idx, field_map)
            records.append(record)

        # Generate content embeddings in batch
        contents = [r['searchable_content'] for r in records]
        content_embeddings = self.embedder.generate_batch(
            contents, batch_size=self.embedding_batch_size
        )

        # Generate title embeddings in batch
        titles = [r.get('title') or '' for r in records]
        title_embeddings = self.embedder.generate_batch(
            titles, batch_size=self.embedding_batch_size
        )

        # Add embeddings to records
        for i, record in enumerate(records):
            record['content_embedding'] = content_embeddings[i]
            record['title_embedding'] = title_embeddings[i]

        # Bulk insert to database
        inserted = self.db.bulk_insert(records)
        return inserted

    def _extract_record(
        self, row: pd.Series, source_file: str,
        row_num: int, field_map: Dict
    ) -> Dict:
        """Extract and transform a single CSV row."""

        # Get mapped fields
        title = self._get_field_value(row, field_map.get('title'))
        description = self._get_field_value(row, field_map.get('description'))
        category = self._get_field_value(row, field_map.get('category'))
        tags_raw = self._get_field_value(row, field_map.get('tags'))

        # Parse tags (comma-separated string to list)
        tags = None
        if tags_raw:
            tags = [t.strip() for t in str(tags_raw).split(',') if t.strip()]

        # Build searchable content from all text fields
        searchable_parts = []

        # Add mapped fields
        if title:
            searchable_parts.append(title)
        if description:
            searchable_parts.append(description)
        if category:
            searchable_parts.append(f"Category: {category}")
        if tags:
            searchable_parts.append(f"Tags: {', '.join(tags)}")

        # Add all other text fields that weren't mapped
        mapped_columns = set(v for v in field_map.values() if v)
        for col in row.index:
            if col not in mapped_columns and pd.notna(row[col]):
                value = str(row[col]).strip()
                if value and len(value) > 2:
                    searchable_parts.append(f"{col}: {value}")

        searchable_content = " | ".join(filter(None, searchable_parts))

        # Fallback: if no searchable content, use all columns
        if not searchable_content.strip():
            searchable_content = " | ".join(
                f"{col}: {val}" for col, val in row.items() if pd.notna(val)
            )

        # Convert raw data, handling NaN values
        raw_data = {}
        for col, val in row.items():
            if pd.notna(val):
                raw_data[col] = val
            else:
                raw_data[col] = None

        return {
            'source_file': source_file,
            'row_number': row_num,
            'raw_data': raw_data,
            'title': title,
            'description': description,
            'category': category,
            'tags': tags,
            'searchable_content': searchable_content,
            'content_embedding': None,
            'title_embedding': None,
            'metadata': {
                'original_columns': list(row.index),
                'field_mapping': field_map
            }
        }

    def _get_field_value(self, row: pd.Series, column_name: Optional[str]) -> Optional[str]:
        """Safely get a field value from a row."""
        if column_name is None:
            return None
        if column_name not in row.index:
            return None
        value = row[column_name]
        if pd.isna(value):
            return None
        return str(value).strip()
