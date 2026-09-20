from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('users/', views.users_page, name='users'),

    path('provider-verification/', views.provider_verification, name='provider_verification'),
    path('provider-verification/<int:user_id>/approve/', views.approve_provider, name='approve_provider'),
    path('provider-verification/<int:user_id>/reject/', views.reject_provider, name='reject_provider'),
    
    path('vehicle-verification/', views.vehicle_verification, name='vehicle_verification'),
    path('vehicle-verification/<int:vehicle_id>/approve/', views.approve_vehicle, name='approve_vehicle'),
    path('vehicle-verification/<int:vehicle_id>/reject/', views.reject_vehicle, name='reject_vehicle'),

    path('deliveries/', views.deliveries, name='deliveries'),

    path('escrow-payments/', views.escrow_payments, name='escrow'),

    path('ratings-feedback/', views.ratings_feedback, name='feedback'),
    path('reports/', views.reports, name='reports'),
    path('settings/', views.settings_page, name='settings'),
    path('logout/', views.custom_logout, name='logout'),
    
    # CHANGED: 'admin/' to 'dashboard/' to prevent Django default admin conflicts
    path('dashboard/messages/', views.messages_view, name='messages'),
    path('dashboard/messages/<int:room_id>/thread/', views.message_thread_api, name='message_thread'),
    path('dashboard/messages/<int:room_id>/send/', views.send_message_api, name='send_message'),
    path('dashboard/support/', views.admin_support_view, name='admin_support'),
]