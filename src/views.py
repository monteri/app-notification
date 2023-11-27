import json
from datetime import datetime
import time
import uuid

import boto3
import redis
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
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
        task_id = str(uuid.uuid4())
        status = 'in_queue'
        try:
            table.put_item(
                Item={
                    'task_id': task_id,
                    'task_status': status,
                    'created_at': datetime.now().isoformat()
                }
            )
            response = sqs.send_message(
                QueueUrl=settings.SQS_URL,
                MessageBody=task_id,
                MessageGroupId='tasks_group',
                MessageDeduplicationId=task_id
            )
            timestamp = time.time()
            redis_client.zadd('tasks_queue', {task_id: timestamp})
            redis_client.setex(f"task_status_{task_id}", 600, status)
            print(response)

        except Exception as e:
            # Handle any exceptions (like issues with AWS connection)
            print(e)
            return JsonResponse({'error': 'Failed to add task to SQS'}, status=500)

        # Return some information about the task
        return JsonResponse({'task_id': task_id, 'status': status})

    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)


def stream_task_status(request):
    def event_stream():
        while True:
            for key in redis_client.scan_iter("task_status_*"):
                task_id = key.decode("utf-8").split("_")[2]
                status = redis_client.get(key).decode("utf-8")

                # Check for position if the status is in_queue
                if status == 'in_queue':
                    position = redis_client.zrank('tasks_queue', task_id)
                    if position is not None:
                        status = f"In queue: {position + 1}"

                # Make status user-friendly
                status = status.replace('_', ' ').capitalize()

                data = {'task_id': task_id, 'status': status}
                yield f"data: {json.dumps(data)}\n\n"
            time.sleep(5)  # Check every 5 seconds

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


def task_view(request):
    return render(request, 'add_task.html')
