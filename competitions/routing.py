from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/competitions/<int:competition_pk>/', consumers.ScoreUpdateConsumer.as_asgi()),  # Use as_asgi()
]