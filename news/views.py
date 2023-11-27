from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from allauth.account.views import SignupView
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView, UpdateView, CreateView, DeleteView, ListView
from .models import Post, Group, Category
from .forms import PostForm
from django.contrib.auth.views import LoginView as AuthLoginView
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from django.http import JsonResponse
import ssl
from smtplib import SMTP_SSL
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from .signals import post_save_news
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.dispatch import Signal
from .tasks import send_notification_to_subscribers
import logging

post_save_news = Signal()
logger = logging.getLogger(__name__)


class NewsListView(ListView):
    model = Post
    template_name = 'news/news_list.html'
    context_object_name = 'news'
    ordering = ['-created_at']
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super(NewsListView, self).get_context_data(**kwargs)

        paginator = context['paginator']
        current_page = self.request.GET.get('page', 1)
        news = paginator.get_page(current_page)

        start_range = max(news.number - 5, 1)
        end_range = min(news.number + 4, paginator.num_pages)

        context['news'] = news
        context['paginator'] = paginator
        context['start_range'] = start_range
        context['end_range'] = end_range
        context['current_page'] = news.number
        context['news_count'] = Post.objects.filter(post_type='news').count()
        context['is_common_user'] = not self.request.user.groups.filter(name='authors').exists()
        return context


class NewsDetailView(DetailView):
    model = Post
    template_name = 'news/news_detail.html'
    context_object_name = 'news'

    def get_context_data(self, **kwargs):
        context = super(NewsDetailView, self).get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            news = self.get_object()
            context['category_subscribed'] = \
                (self.request.user.subscribed_categories.filter(pk__in=news.categories.all()).exists())
        return context


class SearchView(ListView):
    model = Post
    template_name = 'news/search.html'
    context_object_name = 'search_results'

    def get_queryset(self):
        return Post.objects.all()


class SearchResultView(ListView):
    model = Post
    template_name = 'news/search_results.html'
    context_object_name = 'search_results'
    paginate_by = 10

    def get_queryset(self):
        query_title = self.request.GET.get('title')
        query_author = self.request.GET.get('author')
        query_date = self.request.GET.get('date')

        queryset = Post.objects.all()

        if query_title:
            queryset = queryset.filter(title__icontains=query_title)

        if query_author:
            queryset = queryset.filter(author__username__icontains=query_author)

        if query_date:
            queryset = queryset.filter(created_at__gte=query_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super(SearchResultView, self).get_context_data(**kwargs)
        search_results = context['search_results']

        paginator = Paginator(search_results, self.paginate_by)
        current_page = self.request.GET.get('page', 1)
        search_results = paginator.get_page(current_page)

        start_range = max(search_results.number - 5, 1)
        end_range = min(search_results.number + 4, paginator.num_pages)

        context['search_results'] = search_results
        context['paginator'] = paginator
        context['start_range'] = start_range
        context['end_range'] = end_range
        context['current_page'] = search_results.number

        return context


class CustomSignupView(SignupView):
    template_name = 'account/signup.html'
    success_url = reverse_lazy('account_login')


class LoginView(AuthLoginView):
    template_name = 'account/login.html'


class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    fields = ['username', 'email']
    template_name = 'user_update.html'
    success_url = reverse_lazy('profile')

    def get_object(self, queryset=None):
        return self.request.user


class NewsCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Post
    template_name = 'news/news_create.html'
    form_class = PostForm
    success_url = reverse_lazy('news:news_list')
    context_object_name = 'news'

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.post_type = 'news'
        response = super().form_valid(form)
        send_notification_to_subscribers.delay(form.instance.pk)
        return response

    def test_func(self):
        return self.request.user.groups.filter(name='authors').exists()


class NewsUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Post
    template_name = 'news/news_edit.html'
    form_class = PostForm
    context_object_name = 'news'
    success_url = reverse_lazy('news:news_list')

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.post_type = 'news'
        response = super().form_valid(form)
        send_notification_to_subscribers.delay(form.instance.pk)
        return response

    def test_func(self):
        return self.request.user.groups.filter(name='authors').exists()


class NewsDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    template_name = 'news/news_delete.html'
    context_object_name = 'news'
    success_url = reverse_lazy('news:news_list')

    def test_func(self):
        return self.request.user.groups.filter(name='authors').exists()


@login_required
def become_author(request):
    user = request.user
    author_group = Group.objects.get(name='authors')
    user.groups.add(author_group)
    return redirect('news:news_list')


def access_denied(request):
    return render(request, 'news/access_denied.html')


@login_required
def toggle_category_subscription(request, category_id, subscribed):
    category = get_object_or_404(Category, id=category_id)
    user = request.user

    if subscribed == 1:
        category.subscribers.add(user)
    else:
        category.subscribers.remove(user)

        category.subscribers.remove(user)

        category.subscribers.remove(user)

    return JsonResponse({'subscribed': category.subscribers.filter(id=user.id).exists()})


def generate_email_content(post):
    html_content = f'<h1>{post.title}</h1>'
    html_content += f'<p>Содержимое новости:{post.content[:50]}</p>'
    return html_content


def my_view(request):
    logger.debug('Debug message')  # Не будет выведено в консоль, если DEBUG=True
    logger.info('Info message')  # Будет выведено в консоль и general.log
    logger.warning('Warning message')  # Будет выведено в консоль и general.log
    logger.error('Error message')  # Будет выведено в консоль, errors.log, security.log и отправлено на почту
    logger.critical('Critical message')  # Будет выведено в консоль, errors.log, security.log и отправлено на почту
