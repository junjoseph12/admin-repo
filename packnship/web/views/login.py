# views/login.py
from django.shortcuts import render, redirect
from functools import wraps


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get('is_mock_logged_in'):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped


MOCK_CONVERSATIONS = [
    {
        'room_id': 'room_1001',
        'delivery_id': '1001',
        'sender': 'Jonel Jumawan',
        'provider': 'Jun Joseph Pestaño',
        'last_message': 'Please ensure contactless handover if possible.',
        'updated_at': '10:14 AM',
        'messages': [
            {'sender_id': 301, 'sender_name': 'Jonel Jumawan', 'sender_role': 'sender', 'message': 'Hello, is my delivery confirmed?', 'sent_at': '10:10 AM'},
            {'sender_id': 402, 'sender_name': 'Jun Joseph Pestaño', 'sender_role': 'provider', 'message': 'Yes, accepting it now.', 'sent_at': '10:12 AM'},
            {'sender_id': 0, 'sender_name': 'Admin', 'sender_role': 'admin', 'message': 'Please ensure contactless handover if possible.', 'sent_at': '10:14 AM'}
        ]
    },
    {
        'room_id': 'room_1002',
        'delivery_id': '1002',
        'sender': 'Kornel Jumao-as',
        'provider': 'Jun Joseph Pestaño',
        'last_message': 'Escrow frozen temporarily while investigating.',
        'updated_at': 'Yesterday',
        'messages': [
            {'sender_id': 402, 'sender_name': 'Jun Joseph Pestaño', 'sender_role': 'provider', 'message': 'Route is blocked due to roadwork.', 'sent_at': 'Yesterday 2:30 PM'},
            {'sender_id': 0, 'sender_name': 'Admin', 'sender_role': 'admin', 'message': 'Escrow frozen temporarily while investigating.', 'sent_at': 'Yesterday 2:40 PM'}
        ]
    }
]


def admin_login(request):
    if request.session.get('is_mock_logged_in'):
        return redirect('dashboard')

    error_message = None
    if request.method == 'POST':
        u = (request.POST.get('username') or '').strip()
        p = request.POST.get('password') or ''

        if u == 'admin' and p == 'admin':
            request.session['is_mock_logged_in'] = True
            request.session['admin_first_name']  = 'Admin'
            request.session['admin_last_name']   = 'PackNShip'
            request.session['admin_email']       = 'admin@packnship.local'
            return redirect('dashboard')
        else:
            error_message = "Invalid credentials. Please use admin / admin."

    return render(request, 'pages/login.html', {'error_message': error_message})


def custom_logout(request):
    for k in ['is_mock_logged_in', 'admin_first_name', 'admin_last_name', 'admin_email']:
        request.session.pop(k, None)
    return redirect('login')