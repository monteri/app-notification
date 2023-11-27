import time

from django.conf import settings
from django.core.management.base import BaseCommand
import boto3
import redis


sqs = boto3.client('sqs')
redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('tasks-queue')
sns = boto3.client('sns')
topic_arn = settings.SNS_TOPIC_ARN


def update_task_to_processing(task_id):
    redis_client.setex(f"task_status_{task_id}", 600, 'processing')
    table.update_item(
        Key={'task_id': task_id},
        UpdateExpression='SET task_status = :val',
        ExpressionAttributeValues={':val': 'processing'}
    )
    print(f'Updated record in DynamoDB for status - processing')


def mark_task_complete(task_id, is_success):
    status = 'success' if is_success else 'error'
    redis_client.setex(f"task_status_{task_id}", 600, status)
    table.update_item(
        Key={'task_id': task_id},
        UpdateExpression='SET task_status = :val',
        ExpressionAttributeValues={':val': status}
    )
    print(f'Updated record in DynamoDB for status - {status}')
    message = f'Task {task_id} updated to {status}'
    sns.publish(
        TopicArn=topic_arn,
        Message=message,
        Subject='Task Status Update'
    )
    print('Published in SNS')


class Command(BaseCommand):
    help = 'Process tasks from SQS queue and Redis sorted set'

    def handle(self, *args, **options):
        while True:
            # Receive message from SQS
            response = sqs.receive_message(
                QueueUrl=settings.SQS_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20  # Long polling
            )

            if 'Messages' in response:
                for message in response['Messages']:
                    task_id = message['Body']
                    print(f'Started processing {task_id}')
                    redis_client.zrem('tasks_queue', task_id)
                    update_task_to_processing(task_id)
                    time.sleep(10)
                    sqs.delete_message(
                        QueueUrl=settings.SQS_URL,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    mark_task_complete(task_id, True)
                    print(f'Completed processing {task_id}')

            self.stdout.write(self.style.SUCCESS('Successfully processed queue'))
