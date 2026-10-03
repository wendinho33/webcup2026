from django.urls import path

from . import views

app_name = 'terra'

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('mission-control/', views.dashboard, name='dashboard'),
]
