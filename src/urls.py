from django.urls import path
from .views import add_task, task_view, check_task_status

urlpatterns = [
    path('', task_view, name='task-view'),
    path('add-task/', add_task, name='add-task'),
    path('check-task-status/<str:task_id>', check_task_status, name='check-task-status')
]
