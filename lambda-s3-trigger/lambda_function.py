import json
import boto3
import os
from urllib.parse import unquote_plus
from datetime import datetime

sqs = boto3.client('sqs')
QUEUE_URL = os.environ['SQS_QUEUE_URL']

def lambda_handler(event, context):
    """Handle S3 event notifications for new CSV uploads."""
    
    processed = 0
    skipped = 0
    errors = 0
    
    for record in event.get('Records', []):
        try:
            # Get S3 event details
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            size = record['s3']['object'].get('size', 0)
            
            print(f"Received event for: s3://{bucket}/{key} (size: {size} bytes)")
            
            # Only process CSV files in the incoming/ folder
            if not key.startswith('incoming/'):
                print(f"Skipping: not in incoming/ folder: {key}")
                skipped += 1
                continue
            
            if not key.lower().endswith('.csv'):
                print(f"Skipping: not a CSV file: {key}")
                skipped += 1
                continue
            
            # Skip the folder placeholder object
            if key == 'incoming/' or size == 0:
                print(f"Skipping: empty object or folder placeholder: {key}")
                skipped += 1
                continue
            
            # Create job message
            message = {
                'bucket': bucket,
                'key': key,
                'size': size,
                'filename': key.split('/')[-1],
                'event_time': record['eventTime'],
                'triggered_at': datetime.utcnow().isoformat()
            }
            
            # Send to SQS
            response = sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'source': {
                        'DataType': 'String',
                        'StringValue': 's3-trigger'
                    },
                    'filename': {
                        'DataType': 'String',
                        'StringValue': key.split('/')[-1]
                    }
                }
            )
            
            print(f"Queued job for: {key} (MessageId: {response['MessageId']})")
            processed += 1
            
        except Exception as e:
            print(f"Error processing record: {e}")
            errors += 1
    
    result = {
        'statusCode': 200,
        'body': {
            'processed': processed,
            'skipped': skipped,
            'errors': errors
        }
    }
    
    print(f"Result: {json.dumps(result)}")
    return result
