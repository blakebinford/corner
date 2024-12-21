from django.urls import re_path

from . import consumers, organizer_consumer

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_name>\w+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/organizer_chat/(?P<competition_id>\d+)/$', organizer_consumer.OrganizerChatConsumer.as_asgi()),
]