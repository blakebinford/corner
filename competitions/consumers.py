from channels.generic.websocket import AsyncWebsocketConsumer
import json

class ScoreUpdateConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.competition_id = self.scope['url_route']['kwargs']['competition_pk']
        self.competition_group_name = f'competition_{self.competition_id}'

        # Join competition group
        await self.channel_layer.group_add(
            self.competition_group_name,
            self.channel_name
        )

        await self.accept()

        # Print statement to check connection and competition_pk
        print(f"WebSocket connection established to competition_pk: {self.competition_id}")

    async def disconnect(self, close_code):
        # Leave competition group
        await self.channel_layer.group_discard(
            self.competition_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']

        # Send message to competition group
        await self.channel_layer.group_send(
            self.competition_group_name,
            {
                'type': 'score_update',
                'message': message
            }
        )

    # Receive message from competition group
    async def score_update(self, event):
        message = event['message']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message
        }))