import os

class Config:
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL')
    DB_SECRET_NAME = os.getenv('DB_SECRET_NAME', 'llm-db-credentials')
    EMBED_MODEL_ID = os.getenv('EMBED_MODEL_ID', 'sentence-transformers/all-MiniLM-L6-v2')
    BATCH_SIZE = int(os.getenv('BATCH_SIZE', '100'))
    EMBEDDING_BATCH_SIZE = int(os.getenv('EMBEDDING_BATCH_SIZE', '32'))
    
    # Field mapping configuration
    # These define which CSV columns map to which database fields
    TITLE_FIELDS = os.getenv('TITLE_FIELDS', 'title,name,heading,subject').split(',')
    DESCRIPTION_FIELDS = os.getenv('DESCRIPTION_FIELDS', 'description,content,text,body,summary').split(',')
    CATEGORY_FIELDS = os.getenv('CATEGORY_FIELDS', 'category,type,class,group').split(',')
    TAG_FIELDS = os.getenv('TAG_FIELDS', 'tags,keywords,labels').split(',')
