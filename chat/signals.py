from django.db.models.signals import post_save
from django.dispatch import receiver
from competitions.models import Competition
from .models import ChatRoom, OrganizerChatRoom

@receiver(post_save, sender=Competition)
def create_chat_room(sender, instance, created, **kwargs):
    if created:
        ChatRoom.objects.create(competition=instance)

@receiver(post_save, sender=Competition)
def create_organizer_chat_room(sender, instance, created, **kwargs):
    if created:
        OrganizerChatRoom.objects.create(competition=instance)
