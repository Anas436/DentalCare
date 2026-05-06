from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_page, name='chat'),
    path('api/message/', views.chat_message, name='chat_message'),
]
