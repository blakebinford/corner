from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    # ... other URLs
    path('like_message/', views.like_message, name='like_message'),
]
