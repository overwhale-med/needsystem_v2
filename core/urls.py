from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # หน้า Dashboard (หน้าแรก)
    path('', views.dashboard, name='dashboard'),

    # เส้นทาง Login
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),

    # เส้นทาง Logout
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]