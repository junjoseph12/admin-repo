# views/admin_logs.py
from django.shortcuts import render
from django.db import connection
from .login import admin_required
from datetime import timedelta  # ✅ Import timedelta

@admin_required
def admin_logs_view(request):
    logs = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    al.log_id, 
                    al.action, 
                    al.created_at, 
                    u.first_name, 
                    u.last_name,
                    u.email
                FROM public.admin_logs al
                LEFT JOIN public.users u ON u.user_id = al.admin_id
                ORDER BY al.created_at DESC
                LIMIT 100
            """)
            
            for row in cursor.fetchall():
                log_id, action, created_at, first_name, last_name, email = row
                
                # Construct admin name
                admin_name = " ".join(filter(None, [first_name, last_name])) or f"Admin #{row[3] if row[3] else 'Unknown'}"
                
                # ✅ Add 8 hours to the timestamp before formatting
                local_time = created_at
                if created_at:
                    # Assume the DB time is UTC, so we add 8 hours for PHT
                    local_time = created_at + timedelta(hours=8)
                
                logs.append({
                    'id': log_id,
                    'action': action,
                    'timestamp': local_time.strftime('%b %d, %Y — %I:%M %p') if local_time else '—',
                    'admin_name': admin_name,
                    'admin_email': email or '—'
                })
                
    except Exception as e:
        print(f"[admin_logs] DB error: {e}")

    return render(request, 'pages/admin_logs.html', {'logs': logs})