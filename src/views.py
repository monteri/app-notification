from datetime import datetime
import time
import uuid

import boto3
import redis
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

sqs = boto3.client(
                'sqs',
                region_name='eu-west-1',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('tasks-queue')

redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0)


@csrf_exempt
def add_task(request):
    if request.method == 'POST':
        # Create a new Task instance

        task_id = str(uuid.uuid4())
        status = 'in_queue'
        response = table.put_item(
            Item={
                'task_id': task_id,
                'task_status': status,
                'created_at': datetime.now().isoformat()
            }
        )
        try:
            response = sqs.send_message(
                QueueUrl=settings.SQS_URL,
                MessageBody=task_id,  # You can send any relevant data here
                MessageGroupId='tasks_group',
                MessageDeduplicationId=task_id
            )
            timestamp = time.time()
            redis_client.zadd('tasks_queue', {task_id: timestamp})
            # You might want to log the response or handle it as needed
            print(response)

        except Exception as e:
            # Handle any exceptions (like issues with AWS connection)
            print(e)
            return JsonResponse({'error': 'Failed to add task to SQS'}, status=500)

        # Return some information about the task
        return JsonResponse({'task_id': task_id, 'status': status})

    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def check_task_status(request, task_id):
    # Check Redis for the task's position
    position = redis_client.zrank('tasks_queue', task_id)
    if position is not None:
        return JsonResponse({'status': f"In queue: {position + 1}"})

    # If not in Redis, check DynamoDB
    response = table.get_item(Key={'task_id': task_id})
    if 'Item' in response:
        return JsonResponse({'status': response['Item']['task_status']})
    else:
        return JsonResponse({'status': 'Not found'}, status=404)


def task_view(request):
    return render(request, 'add_task.html')
