from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('users/', views.users_page, name='users'),
    path('admin-logs/', views.admin_logs_view, name='admin_logs'),

    # User status toggle (both endpoints registered so users.html fetch('/toggle-user-status/') works)
    path('toggle-user-status/', views.toggle_user_status, name='toggle_user_status'),
    path('api/users/toggle-status/', views.toggle_user_status, name='api_toggle_user_status'),

    # Blockchain Ledger & Audit Explorer
    path('blockchain-ledger/', views.blockchain_ledger_page, name='blockchain_ledger'),
    path('blockchain-ledger/sync/', views.sync_unanchored_records, name='sync_unanchored_records'),
    path('api/blockchain/verify/', views.verify_tx_hash_api, name='verify_tx_hash_api'),

    path('provider-verification/', views.provider_verification, name='provider_verification'),
    path('provider-verification/<int:user_id>/approve/', views.approve_provider, name='approve_provider'),
    path('provider-verification/<int:user_id>/reject/', views.reject_provider, name='reject_provider'),
    path('provider-verification/<int:user_id>/photo/<str:kind>/', views.provider_photo, name='provider_photo'),

    path('vehicle-verification/', views.vehicle_verification, name='vehicle_verification'),
    path('vehicle-verification/<int:vehicle_id>/approve/', views.approve_vehicle, name='approve_vehicle'),
    path('vehicle-verification/<int:vehicle_id>/reject/', views.reject_vehicle, name='reject_vehicle'),
    path('vehicle-verification/<int:vehicle_id>/document/', views.vehicle_document, name='vehicle_document'),

    path('deliveries/', views.deliveries, name='deliveries'),

    path('messages/', views.admin_support_view, name='messages'),
    path('api/chat/rooms/start/', views.chat_start_room_api, name='chat_start_room_api'),
    path('api/chat/rooms/<int:room_id>/thread/', views.chat_thread_api, name='chat_thread_api'),
    path('api/chat/rooms/<int:room_id>/send/', views.chat_send_api, name='chat_send_api'),

    path('escrow-payments/', views.escrow_payments, name='escrow'),
    path('escrow-payments/action/', views.process_escrow_action, name='escrow_action'),
    path('escrow-payments/freeze/', views.toggle_escrow_freeze, name='escrow_freeze'),

    path('disputes/', views.admin_disputes_view, name='admin_disputes'),
    path('api/disputes/list/', views.disputes_list_api, name='disputes_list_api'),
    path('api/disputes/<int:dispute_id>/', views.dispute_detail_api, name='dispute_detail_api'),
    path('api/disputes/<int:dispute_id>/resolve/', views.dispute_resolve_api, name='dispute_resolve_api'),
    path('api/disputes/<int:dispute_id>/dismiss/', views.dispute_dismiss_api, name='dispute_dismiss_api'),

    path('ratings-feedback/', views.ratings_feedback, name='feedback'),
    path('reports/', views.reports, name='reports'),
    path('settings/', views.settings_page, name='settings'),
    path('logout/', views.custom_logout, name='logout'),

    path('api/support/tickets/', views.support_tickets_api, name='support_tickets_api'),
    path('api/support/tickets/<int:ticket_id>/', views.support_thread_api, name='support_thread_api'),
    path('api/support/tickets/<int:ticket_id>/reply/', views.support_reply_api, name='support_reply_api'),
    path('api/support/tickets/<int:ticket_id>/status/', views.support_status_api, name='support_status_api'),

    # CHANGED: 'admin/' to 'dashboard/' to prevent Django default admin conflicts
    path('dashboard/support/', views.admin_support_view, name='admin_support'),
]