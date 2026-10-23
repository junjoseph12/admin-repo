# views/utils.py
from django.db import connection

def log_admin_action(request, action_text):
    """
    Logs an admin action into public.admin_logs using the logged-in user's email or username.
    """
    if not request.user.is_authenticated:
        return

    admin_email = request.user.email
    admin_username = request.user.username

    try:
        with connection.cursor() as cursor:
            admin_id = None
            
            # 1. Try to find the user_id by email
            if admin_email:
                cursor.execute("SELECT user_id FROM public.users WHERE email = %s LIMIT 1", [admin_email])
                row = cursor.fetchone()
                if row:
                    admin_id = row[0]
            
            # 2. If not found, try by username (first_name)
            if not admin_id and admin_username:
                cursor.execute("SELECT user_id FROM public.users WHERE first_name = %s LIMIT 1", [admin_username])
                row = cursor.fetchone()
                if row:
                    admin_id = row[0]
            
            # 3. Fallback: If still not found, just use the very first user ID as the admin
            if not admin_id:
                cursor.execute("SELECT user_id FROM public.users ORDER BY user_id LIMIT 1")
                row = cursor.fetchone()
                if row:
                    admin_id = row[0]

            if not admin_id:
                print(f"[log_admin_action] Failed: No admin user found in public.users.")
                return

            # Insert the log
            cursor.execute("""
                INSERT INTO public.admin_logs (admin_id, action)
                VALUES (%s, %s)
            """, [admin_id, action_text])
            
            print(f"[log_admin_action] Success: '{action_text}' logged for Admin ID {admin_id}.")
            
    except Exception as e:
        print(f"[log_admin_action] DB Error: {e}")