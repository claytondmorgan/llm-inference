import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
import json
import boto3
import os
import uuid
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.creds = self._get_credentials()
        logger.info(f"Database manager initialized for host: {self.creds['host']}")

    def _get_credentials(self):
        """Get database credentials from Secrets Manager."""
        secret_name = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
        region = os.getenv('AWS_REGION', 'us-east-1')

        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])

    def _get_connection(self):
        """Create a new database connection."""
        return psycopg2.connect(
            host=self.creds['host'],
            database=self.creds['database'],
            user=self.creds['username'],
            password=self.creds['password'],
            port=self.creds['port']
        )

    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def create_job(self, source_file: str) -> str:
        """Create a new ingestion job record."""
        job_id = str(uuid.uuid4())

        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO ingestion_jobs (job_id, source_file, status, started_at)
            VALUES (%s, %s, 'processing', NOW())
            RETURNING id
            """,
            (job_id, source_file)
        )

        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Created job {job_id} for {source_file}")
        return job_id

    def update_job(self, job_id: str, **kwargs):
        """Update job status and progress."""
        conn = self._get_connection()
        cur = conn.cursor()

        updates = []
        values = []

        for key, value in kwargs.items():
            updates.append(f"{key} = %s")
            values.append(value)

        if 'status' in kwargs and kwargs['status'] in ('completed', 'completed_with_errors', 'failed'):
            updates.append("completed_at = NOW()")

        values.append(job_id)

        cur.execute(
            f"UPDATE ingestion_jobs SET {', '.join(updates)} WHERE job_id = %s",
            values
        )

        conn.commit()
        cur.close()
        conn.close()

    def bulk_insert(self, records: List[Dict]) -> int:
        """Bulk insert records into ingested_records table."""
        if not records:
            return 0

        conn = self._get_connection()
        cur = conn.cursor()

        values = []
        for r in records:
            values.append((
                r['source_file'],
                r['row_number'],
                json.dumps(r['raw_data'], default=str),
                r.get('title'),
                r.get('description'),
                r.get('category'),
                r.get('tags'),
                r['searchable_content'],
                r.get('content_embedding'),
                r.get('title_embedding'),
                json.dumps(r.get('metadata', {}))
            ))

        execute_values(
            cur,
            """
            INSERT INTO ingested_records
            (source_file, row_number, raw_data, title, description, category,
             tags, searchable_content, content_embedding, title_embedding, metadata)
            VALUES %s
            """,
            values,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::vector, %s)"
        )

        inserted = len(values)
        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Inserted {inserted} records")
        return inserted

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get the status of an ingestion job."""
        conn = self._get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            "SELECT * FROM ingestion_jobs WHERE job_id = %s",
            (job_id,)
        )

        result = cur.fetchone()
        cur.close()
        conn.close()

        return dict(result) if result else None
