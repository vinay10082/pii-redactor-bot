import json
import os
import uuid
import boto3

sqs = boto3.client('sqs')
dynamodb = boto3.client('dynamodb')

QUEUE_URL = os.environ.get('QUEUE_URL')
RESULTS_TABLE = os.environ.get('RESULTS_TABLE', 'PII_Results')

def lambda_handler(event, context):
    try:
        # Check if this is a GET request (polling for result)
        if event.get('httpMethod') == 'GET':
            job_id = event.get('queryStringParameters', {}).get('jobId')
            if not job_id:
                return {'statusCode': 400, 'body': json.dumps({'error': 'Missing jobId'})}
                
            response = dynamodb.get_item(
                TableName=RESULTS_TABLE,
                Key={'JobId': {'S': job_id}}
            )
            
            if 'Item' in response:
                return {
                    'statusCode': 200,
                    'headers': {'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({
                        'status': 'COMPLETED',
                        'clean_text': response['Item']['CleanText']['S']
                    })
                }
            else:
                return {
                    'statusCode': 200,
                    'headers': {'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'status': 'PROCESSING'})
                }

        # Handle POST request (new text to redact)
        body = json.loads(event.get('body', '{}'))
        raw_text = body.get('text', '')
        
        job_id = str(uuid.uuid4())
        
        # Send to SQS
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps({
                'jobId': job_id,
                'text': raw_text
            })
        )
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'jobId': job_id,
                'message': 'Text submitted for async redaction.'
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
