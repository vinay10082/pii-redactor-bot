import json
import re
import os
import time
import uuid
import boto3
import urllib.parse
from datetime import datetime

# Initialize NLP libraries lazily to improve cold start slightly
spacy = None
nlp = None
langdetect = None

dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
TABLE_NAME = os.environ.get('AUDIT_TABLE', 'PII_Audit_Log')
PROCESSED_BUCKET = os.environ.get('PROCESSED_BUCKET')
RESULTS_TABLE = os.environ.get('RESULTS_TABLE', 'PII_Results')

def load_nlp():
    global spacy, nlp, langdetect
    if spacy is None:
        try:
            import spacy as sp
            import langdetect as ld
            spacy = sp
            langdetect = ld
            # Load the small english model installed in the layer
            nlp = spacy.load('en_core_web_sm')
        except ImportError:
            print("WARNING: spacy or langdetect not found. Falling back to regex-only redaction.")
            spacy = False
            langdetect = False

def process_text(raw_text):
    load_nlp()
    
    # 1. Detect Language (Multi-language Support requirement)
    try:
        lang = langdetect.detect(raw_text)
    except:
        lang = 'en'
    
    scrubbed_text = raw_text
    found_types = set()
    
    # 2. Contextual Redaction (NLP/AI) using SpaCy
    if spacy:
        doc = nlp(scrubbed_text)
        
        # SpaCy entity types we consider PII
        pii_entities = {'PERSON', 'ORG', 'GPE', 'LOC', 'FAC', 'DATE'}
        
        # We must process entities in reverse order to not mess up indices during replacement
        for ent in reversed(doc.ents):
            if ent.label_ in pii_entities:
                # Check context: e.g. "The total is $555" (MONEY) vs "Call John" (PERSON)
                if ent.label_ == 'PERSON':
                    scrubbed_text = scrubbed_text[:ent.start_char] + '[REDACTED NAME]' + scrubbed_text[ent.end_char:]
                    found_types.add('NAME')
                elif ent.label_ in ['ORG', 'GPE', 'LOC']:
                    scrubbed_text = scrubbed_text[:ent.start_char] + '[REDACTED LOCATION/ORG]' + scrubbed_text[ent.end_char:]
                    found_types.add('LOCATION/ORG')
                
                
    # 3. Country-specific rules based on detected language
    if lang == 'en':
        # US/UK specific regexes
        if re.search(r'\b\d{3}-\d{2}-\d{4}\b', scrubbed_text):
            scrubbed_text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED SSN]', scrubbed_text)
            found_types.add('SSN')
        if re.search(r'\b[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}[0-9]{6}[A-D\s]{1}\b', scrubbed_text, re.IGNORECASE):
            scrubbed_text = re.sub(r'\b[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}[0-9]{6}[A-D\s]{1}\b', '[REDACTED UK_NI]', scrubbed_text, flags=re.IGNORECASE)
            found_types.add('UK_NI')
    elif lang == 'hi' or lang == 'en': # English could also have Indian Aadhaar
        if re.search(r'\b\d{4}\s\d{4}\s\d{4}\b', scrubbed_text):
            scrubbed_text = re.sub(r'\b\d{4}\s\d{4}\s\d{4}\b', '[REDACTED AADHAAR]', scrubbed_text)
            found_types.add('AADHAAR')
            
    # Generic global regexes (Credit Cards, Phone Numbers)
    if re.search(r'\b(?:\d[ -]*?){13,16}\b', scrubbed_text):
        scrubbed_text = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED CREDIT CARD]', scrubbed_text)
        found_types.add('CREDIT_CARD')
        
    return scrubbed_text, found_types

def log_audit(chars_processed, found_types):
    if not found_types:
        types_str = "NONE"
    else:
        types_str = ",".join(list(found_types))
        
    dynamodb.put_item(
        TableName=TABLE_NAME,
        Item={
            'LogId': {'S': str(uuid.uuid4())},
            'Timestamp': {'S': datetime.utcnow().isoformat()},
            'CharsProcessed': {'N': str(chars_processed)},
            'PiiTypesFound': {'S': types_str}
        }
    )

def lambda_handler(event, context):
    try:
        # Check if event is from SQS
        if 'Records' in event:
            for record in event['Records']:
                # SQS can contain direct text, or an S3 Event notification
                body = record['body']
                try:
                    payload = json.loads(body)
                except:
                    payload = {'text': body}
                    
                # If it's an S3 event triggered via SQS
                if 'Records' in payload and payload['Records'][0].get('eventSource') == 'aws:s3':
                    s3_event = payload['Records'][0]
                    bucket = s3_event['s3']['bucket']['name']
                    key = urllib.parse.unquote_plus(s3_event['s3']['object']['key'])
                    
                    # Read from S3
                    response = s3.get_object(Bucket=bucket, Key=key)
                    raw_text = response['Body'].read().decode('utf-8')
                    
                    scrubbed_text, found_types = process_text(raw_text)
                    log_audit(len(raw_text), found_types)
                    
                    # Write to Processed Bucket
                    out_key = 'clean_' + key
                    s3.put_object(Bucket=PROCESSED_BUCKET, Key=out_key, Body=scrubbed_text.encode('utf-8'))
                    
                else:
                    # Direct text payload from API Gateway
                    raw_text = payload.get('text', '')
                    job_id = payload.get('jobId', str(uuid.uuid4()))
                    scrubbed_text, found_types = process_text(raw_text)
                    log_audit(len(raw_text), found_types)
                    
                    # Save to Results Table for polling
                    dynamodb.put_item(
                        TableName=RESULTS_TABLE,
                        Item={
                            'JobId': {'S': job_id},
                            'CleanText': {'S': scrubbed_text},
                            'ExpirationTime': {'N': str(int(time.time()) + 86400)} # Auto-expire in 24 hours
                        }
                    )
        
        return {'statusCode': 200, 'body': 'Processed successfully'}
    except Exception as e:
        print(f"Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
