from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from .models import Post, Category
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings


@shared_task
def send_weekly_email_notifications():
    subscribed_users = User.objects.filter(subscribed_categories__isnull=False).distinct()

    for user in subscribed_users:
        subscribed_categories = user.subscribed_categories.all()

        last_week = timezone.now() - timezone.timedelta(weeks=1)
        recent_posts = Post.objects.filter(created_at__gte=last_week, categories__in=subscribed_categories).distinct()

        if recent_posts:
            email_subject = "Weekly News Update"
            email_html_message = render_to_string('email/weekly_email.html',
                                                  {'posts': recent_posts, 'username': user.username})
            email_plaintext_message = strip_tags(email_html_message)

            send_mail(
                email_subject,
                email_plaintext_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=email_html_message
            )


@shared_task
def send_notification_to_subscribers(post_id):
    try:
        post = Post.objects.get(pk=post_id)
        categories = post.categories.all()

        if categories:
            for category in categories:
                subscribed_users = category.subscribers.all()

                if subscribed_users:
                    subject = f"Новая новость: {post.title}"
                    html_message = render_to_string('email/news_created_email.html',
                                                    {'news': post, 'username': post.author.username})
                    plain_message = strip_tags(html_message)

                    for user in subscribed_users:
                        send_mail(subject, plain_message, 'projectnewspaper@yandex.ru',
                                  [user.email], html_message=html_message)

    except Post.DoesNotExist:
        pass

