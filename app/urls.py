from django.contrib import admin
from django.urls import path
from . import views



urlpatterns = [
    path('', views.home, name="home"),  # Render home view
    path('register/', views.register, name="register" ),
    path('login/', views.loginPage, name="login" ),
    path('search/', views.search, name="search" ),
    path('category/', views.category, name="category" ),
    path('detail/', views.detail, name="detail" ),
    path('logout/', views.logoutPage, name="logout" ),
    path('cart/', views.cart, name="cart" ),
    path('checkout/', views.checkout, name="checkout" ),
    path('update_item/', views.updateItem, name="update_item" ),
    path('invoice/<int:id>/', views.invoice_detail, name='invoice_detail'),
    path('order-history/', views.order_history, name='order_history'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('profile/', views.profile, name='profile'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
]

