from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Post
from .tasks import send_notification_to_subscribers


@receiver(post_save, sender=Post)
def post_save_news(sender, instance, created, **kwargs):
    if not created:
        send_notification_to_subscribers.delay(instance.pk)