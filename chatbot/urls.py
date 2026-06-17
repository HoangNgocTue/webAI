from django.urls import path
from . import views

urlpatterns = [
    path('', views.chatbot_view, name='chatbot'),
    path('api/', views.chatbot_api, name='chatbot_api'),
    path('product-preview/', views.product_preview_api, name='chatbot_product_preview'),
    path('clear-history/', views.clear_history_api, name='chatbot_clear_history'),
]
