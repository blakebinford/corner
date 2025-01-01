# chat/organizer_consumer.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import OrganizerChatRoom, OrganizerChatMessage
from accounts.models import User

class OrganizerChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.competition_id = self.scope['url_route']['kwargs']['competition_id']
        self.room_group_name = f'organizer_chat_{self.competition_id}'
        self.user = self.scope['user']

        # Check if the user is authorized to join this chat
        if await self.is_authorized():
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']

            saved_message = await self.save_message(message)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'user': self.user.username,
                    'message_id': saved_message.id,
                    'timestamp': saved_message.timestamp.strftime("%I:%M %p"),
                }
            )
            print(f"Message sent by {self.user.username}: {message}")  # Debugging
        except Exception as e:
            print(f"Error in receive method: {e}")  # Debugging

    async def chat_message(self, event):
        print(f"Broadcasting message: {event['message']} from {event['user']}")
        message = event['message']
        user = event['user']  # Assuming `event['user']` is the username
        message_id = event['message_id']
        timestamp = event['timestamp']

        # Fetch the user's first and last name from the database
        user_instance = await database_sync_to_async(User.objects.get)(username=user)
        first_name = user_instance.first_name
        last_name = user_instance.last_name
        user_id = user_instance.id

        await self.send(text_data=json.dumps({
            'message': message,
            'user': user,  # Username
            'first_name': first_name,
            'last_name': last_name,
            'user_id': user_id,
            'message_id': message_id,
            'timestamp': timestamp,
        }))

    @database_sync_to_async
    def save_message(self, message):
        room = OrganizerChatRoom.objects.get(competition_id=self.competition_id)
        saved_message = OrganizerChatMessage.objects.create(room=room, user=self.user, message=message)
        print(f"Message saved: {saved_message.message} by {saved_message.user}")
        return saved_message

    @database_sync_to_async
    def is_authorized(self):
        from competitions.models import Competition  # Avoid Circular Import
        try:
            competition = Competition.objects.get(pk=self.competition_id)
        except Competition.DoesNotExist:
            return False

        if self.user.is_authenticated:
            if self.user == competition.organizer:
                return True
            is_athlete = competition.athletecompetition_set.filter(athlete__user=self.user).exists()
            print(f"User {self.user.username} is athlete: {is_athlete}")  # Debugging
            if is_athlete:
                return True
        return False