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
    path('escrow-payments/action/', views.process_escrow_action, name='escrow_action'),
    path('escrow-payments/freeze/', views.toggle_escrow_freeze, name='escrow_freeze'),

    path('ratings-feedback/', views.ratings_feedback, name='feedback'),
    path('reports/', views.reports, name='reports'),
    path('settings/', views.settings_page, name='settings'),
    path('logout/', views.custom_logout, name='logout'),
    
    path('api/support/tickets/', views.support_tickets_api,  name='support_tickets_api'),
    path('api/support/tickets/<int:ticket_id>/', views.support_thread_api,   name='support_thread_api'),
    path('api/support/tickets/<int:ticket_id>/reply/', views.support_reply_api,    name='support_reply_api'),
    path('api/support/tickets/<int:ticket_id>/status/', views.support_status_api,   name='support_status_api'),
    
    # CHANGED: 'admin/' to 'dashboard/' to prevent Django default admin conflicts
    path('dashboard/support/', views.admin_support_view, name='admin_support'),
]