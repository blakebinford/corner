from django.db import models
from django.conf import settings
from competitions.models import Competition


class ChatRoom(models.Model):
    competition = models.OneToOneField(Competition, on_delete=models.CASCADE, related_name='chat_room')


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'message')

class OrganizerChatRoom(models.Model):
    competition = models.OneToOneField(Competition, on_delete=models.CASCADE, related_name='organizer_chat_room')

    def __str__(self):
        return f"Organizer Chat Room for {self.competition.name}"


class OrganizerChatMessage(models.Model):
    room = models.ForeignKey(OrganizerChatRoom, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.timestamp}: {self.message}"