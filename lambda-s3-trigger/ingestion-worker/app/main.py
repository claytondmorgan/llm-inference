import json
import boto3
import logging
import os
import sys
import time
from app.config import Config
from app.embeddings import EmbeddingGenerator
from app.database import DatabaseManager
from app.processor import CSVProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# AWS clients
sqs = boto3.client('sqs', region_name=Config.AWS_REGION)
s3 = boto3.client('s3', region_name=Config.AWS_REGION)


def move_s3_file(bucket: str, source_key: str, dest_prefix: str):
    """Move a file from one S3 prefix to another."""
    filename = source_key.split('/')[-1]
    dest_key = f"{dest_prefix}/{filename}"

    try:
        # Copy to destination
        s3.copy_object(
            Bucket=bucket,
            CopySource={'Bucket': bucket, 'Key': source_key},
            Key=dest_key
        )
        # Delete original
        s3.delete_object(Bucket=bucket, Key=source_key)
        logger.info(f"Moved s3://{bucket}/{source_key} -> s3://{bucket}/{dest_key}")
    except Exception as e:
        logger.error(f"Failed to move file: {e}")


def process_message(message: dict, processor: CSVProcessor):
    """Process a single SQS message."""
    body = json.loads(message['Body'])
    bucket = body['bucket']
    key = body['key']
    filename = body.get('filename', key.split('/')[-1])

    logger.info(f"Processing file: s3://{bucket}/{key}")

    # Download CSV from S3
    local_path = f"/tmp/{filename}"

    try:
        s3.download_file(bucket, key, local_path)
        logger.info(f"Downloaded to {local_path}")
    except Exception as e:
        logger.error(f"Failed to download {key}: {e}")
        move_s3_file(bucket, key, 'failed')
        return False

    # Process the CSV
    result = processor.process_file(local_path, source_file=key)

    # Move file based on result
    if result.get('success'):
        move_s3_file(bucket, key, 'completed')
        logger.info(
            f"Completed: {result.get('processed_rows', 0)} rows processed, "
            f"{result.get('failed_rows', 0)} failed"
        )
        return True
    else:
        move_s3_file(bucket, key, 'failed')
        logger.error(f"Failed: {result.get('error', 'Unknown error')}")
        return False

    # Clean up temp file
    try:
        os.remove(local_path)
    except:
        pass


def main():
    """Main polling loop."""
    logger.info("=" * 60)
    logger.info("Ingestion Worker Starting")
    logger.info(f"Region: {Config.AWS_REGION}")
    logger.info(f"Queue: {Config.SQS_QUEUE_URL}")
    logger.info(f"Batch Size: {Config.BATCH_SIZE}")
    logger.info(f"Embedding Model: {Config.EMBED_MODEL_ID}")
    logger.info("=" * 60)

    # Validate configuration
    if not Config.SQS_QUEUE_URL:
        logger.error("SQS_QUEUE_URL environment variable is required")
        sys.exit(1)

    # Initialize components
    logger.info("Initializing embedding model...")
    embedder = EmbeddingGenerator(model_name=Config.EMBED_MODEL_ID)

    logger.info("Initializing database connection...")
    db = DatabaseManager()

    if not db.test_connection():
        logger.error("Cannot connect to database. Exiting.")
        sys.exit(1)

    logger.info("Database connection verified")

    # Create processor
    processor = CSVProcessor(embedder=embedder, db=db)

    logger.info("Worker ready. Polling for messages...")

    # Polling loop
    consecutive_errors = 0
    max_consecutive_errors = 10

    while True:
        try:
            # Long poll for messages (wait up to 20 seconds)
            response = sqs.receive_message(
                QueueUrl=Config.SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=900,
                MessageAttributeNames=['All']
            )

            messages = response.get('Messages', [])

            if not messages:
                continue

            for message in messages:
                try:
                    success = process_message(message, processor)

                    # Delete message from queue on success
                    sqs.delete_message(
                        QueueUrl=Config.SQS_QUEUE_URL,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    logger.info("Message deleted from queue")

                    consecutive_errors = 0

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    import traceback
                    traceback.print_exc()
                    consecutive_errors += 1

        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
            break

        except Exception as e:
            logger.error(f"Polling error: {e}")
            consecutive_errors += 1

            if consecutive_errors >= max_consecutive_errors:
                logger.error(
                    f"Too many consecutive errors ({max_consecutive_errors}). Exiting."
                )
                sys.exit(1)

            # Back off on errors
            time.sleep(min(consecutive_errors * 5, 60))


if __name__ == "__main__":
    main()
