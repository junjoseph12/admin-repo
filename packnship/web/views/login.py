# views/login.py
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.shortcuts import render, redirect

# Sign-in throttling: after MAX_ATTEMPTS failures for the same username + IP,
# further attempts are refused for LOCK_SECONDS. (Uses Django's cache, which is
# per-process by default; fine for one admin server.)
MAX_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60


def admin_required(view_func):
    """Allow only a signed-in, active Django staff user (a real admin account).

    Replaces the old check on a hard-coded admin/admin session flag. The name is
    unchanged so every view that imports it keeps working.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff):
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


def _throttle_key(request, username):
    ip = request.META.get('REMOTE_ADDR', '')
    return f"admin-login-fail:{ip}:{username.lower()}"


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('dashboard')

    error_message = None
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        key = _throttle_key(request, username)

        if cache.get(key, 0) >= MAX_ATTEMPTS:
            error_message = "Too many failed attempts. Please wait 15 minutes and try again."
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None and user.is_active and user.is_staff:
                cache.delete(key)
                login(request, user)
                # Kept so the existing admin pages that read these keys still work.
                request.session['is_mock_logged_in'] = True
                request.session['admin_first_name'] = user.first_name or user.get_username()
                request.session['admin_last_name'] = user.last_name or ''
                request.session['admin_email'] = user.email or ''
                return redirect('dashboard')

            cache.set(key, cache.get(key, 0) + 1, LOCK_SECONDS)
            error_message = "Invalid username or password."

    return render(request, 'pages/login.html', {'error_message': error_message})


def custom_logout(request):
    logout(request)  # clears the whole session, including the admin keys
    return redirect('login')