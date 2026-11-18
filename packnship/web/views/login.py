# views/login.py
from functools import wraps
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.shortcuts import render, redirect
from .utils import log_admin_action

MAX_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped


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
            
            if user is not None:
                if not user.is_active:
                    error_message = "This account has been deactivated. Please contact support."
                elif not user.is_staff:
                    error_message = "You do not have permission to access the admin portal."
                else:
                    cache.delete(key)
                    login(request, user)
                    
                    request.session['is_mock_logged_in'] = True
                    request.session['admin_first_name'] = user.first_name or user.get_username()
                    request.session['admin_last_name'] = user.last_name or ''
                    request.session['admin_email'] = user.email or ''
                    
                    # ✅ Log the login action safely
                    try:
                        log_admin_action(request, "Admin logged in")
                    except Exception as e:
                        print(f"Failed to log login action: {e}")
                    
                    return redirect('dashboard')
            else:
                cache.set(key, cache.get(key, 0) + 1, LOCK_SECONDS)
                error_message = "Invalid username or password."

    return render(request, 'pages/login.html', {'error_message': error_message})


def custom_logout(request):
    logout(request)
    return redirect('login')