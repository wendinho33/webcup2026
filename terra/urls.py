from django.urls import path

from . import views

app_name = 'terra'

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('mission-control/', views.dashboard, name='dashboard'),
    path('account/', views.account, name='account'),
    path('account/dossier/', views.account_pdf, name='account_pdf'),
    path('notifications/', views.notifications, name='notifications'),
    path('market/', views.market, name='market'),
    path('market/trade/', views.trade, name='trade'),
    path('market/service/', views.buy_service, name='service'),
    path('chat/', views.chat, name='chat'),
    path('chat/agent/', views.chat_agent, name='chat_agent'),
    path('chat/<int:thread_id>/', views.chat_thread, name='chat_thread'),
    path('chat/<int:thread_id>/send/', views.chat_send, name='chat_send'),
    path(
        'chat/<int:thread_id>/messages/',
        views.chat_messages,
        name='chat_messages',
    ),
    path(
        'chat/<int:thread_id>/action/',
        views.chat_action,
        name='chat_action',
    ),
    path('weather/', views.weather, name='weather'),
    path('weather/api/status/', views.weather_status, name='weather_status'),
    path(
        'weather/api/trigger/',
        views.weather_trigger,
        name='weather_trigger',
    ),
    path('news/', views.news, name='news'),
    path('news/<slug:slug>/', views.news_detail, name='news_detail'),
    path('news/<slug:slug>/comment/', views.news_comment, name='news_comment'),
    path('map/', views.map_view, name='map'),
    path('government/', views.government, name='government'),
    path('government/tax/', views.tax_pay, name='tax_pay'),
    path('government/pension/', views.pension_claim, name='pension_claim'),
    path('government/profile/', views.civic_profile, name='civic_profile'),
    path('requests/', views.civic_request, name='civic_request'),
    path('health/', views.health, name='health'),
    path('health/watch/', views.terra_watch, name='terra_watch'),
    path('transport/', views.transport, name='transport'),
]
