from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import ChatMessage, Like

@require_POST
@login_required
def like_message(request):
    message_id = request.POST.get('message_id')
    action = request.POST.get('action')  # 'like' or 'unlike'

    try:
        message = ChatMessage.objects.get(id=message_id)
        if action == 'like':
            like, created = Like.objects.get_or_create(user=request.user, message=message)
            if not created:
              return JsonResponse({'status': 'error', 'message': 'Already liked'})
        elif action == 'unlike':
            Like.objects.filter(user=request.user, message=message).delete()
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action'})

        likes_count = message.likes.count()
        return JsonResponse({'status': 'ok', 'likes_count': likes_count})

    except ChatMessage.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Message not found'})