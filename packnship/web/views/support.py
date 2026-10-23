# views/support.py
from django.shortcuts import render
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse
from django.db import connection
from django.template.exceptions import TemplateDoesNotExist
import json
from .login import admin_required

ADMIN_EMAIL = 'admin@packnship.com'


@admin_required
def admin_support_view(request):
    try:
        return render(request, 'pages/admin_support_inbox.html')
    except TemplateDoesNotExist:
        return render(request, 'admin_support_inbox.html')


@admin_required
@require_http_methods(["GET"])
def support_tickets_api(request):
    status = request.GET.get('status', 'open')
    search = (request.GET.get('q') or '').strip()

    with connection.cursor() as cur:
        sql = """
            WITH latest_root AS (
                SELECT DISTINCT ON (user_id)
                    notif_id AS ticket_id, user_id, title AS subject,
                    is_read, created_at, body
                FROM notification_log
                WHERE type = 'support' AND ref_id IS NULL
                ORDER BY user_id, created_at DESC
            )
            SELECT
                t.ticket_id, t.user_id, t.subject, t.is_read, t.created_at,
                u.first_name, u.last_name,
                (
                    SELECT r.role_name FROM user_roles ur
                    JOIN roles r ON r.role_id = ur.role_id
                    WHERE ur.user_id = u.user_id
                    ORDER BY ur.role_id ASC LIMIT 1
                ) AS role_name,
                (
                    SELECT body FROM notification_log m
                    WHERE m.ref_id = t.ticket_id
                    ORDER BY m.created_at DESC LIMIT 1
                ) AS last_reply,
                (
                    SELECT MAX(m.created_at) FROM notification_log m
                    WHERE m.ref_id = t.ticket_id
                ) AS last_reply_at,
                (
                    SELECT COUNT(*) FROM notification_log m
                    WHERE m.ref_id = t.ticket_id
                ) AS reply_count,
                t.body AS root_body
            FROM latest_root t
            JOIN users u ON u.user_id = t.user_id
            WHERE 1=1
        """
        params = []
        if search:
            sql += """
              AND (
                u.first_name ILIKE %s OR u.last_name ILIKE %s
                OR t.subject ILIKE %s OR t.body ILIKE %s
              )
            """
            like = f"%{search}%"
            params.extend([like, like, like, like])

        sql += " ORDER BY t.created_at DESC LIMIT 200"
        cur.execute(sql, params)
        rows = cur.fetchall()

    tickets = []
    for r in rows:
        updated = r[9] or r[4]
        tickets.append({
            'id': r[0],
            'user_id': r[1],
            'subject': r[2] or '(no subject)',
            'is_read': r[3],
            'created_at': r[4].isoformat() if r[4] else None,
            'user_name': f"{r[5] or ''} {r[6] or ''}".strip() or f"USR-{r[1]}",
            'role': (r[7] or 'Sender').title(),
            'last_message': r[8] or r[11] or '',
            'updated_at': updated.isoformat() if updated else None,
            'reply_count': r[10] or 0,
            'status': 'open',
        })

    with connection.cursor() as cur:
        for t in tickets:
            cur.execute("""
                SELECT created_at FROM notification_log
                WHERE ref_id = %s AND type = 'support_reply'
                ORDER BY created_at DESC LIMIT 1
            """, [t['id']])
            last = cur.fetchone()
            if last and last[0] and t['created_at']:
                if last[0].isoformat() > t['created_at']:
                    t['status'] = 'pending'

    if status and status != 'all':
        tickets = [t for t in tickets if t['status'] == status]

    return JsonResponse({'tickets': tickets})


@admin_required
@require_http_methods(["GET"])
def support_thread_api(request, ticket_id):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT t.notif_id, t.user_id, t.title, t.is_read, t.created_at, t.body,
                   u.first_name, u.last_name, u.email, u.phone_number,
                   u.created_at AS joined_at,
                   pl.street_address, pl.barangay, pl.city, pl.province,
                   (SELECT balance FROM provider_wallet WHERE provider_id = u.user_id),
                   (SELECT COUNT(*) FROM delivery_requests WHERE sender_id = u.user_id)
                     + (SELECT COUNT(*) FROM deliveries WHERE provider_id = u.user_id),
                   (SELECT ROUND(AVG(rating)::numeric, 1)
                      FROM ratings_reviews WHERE reviewee_id = u.user_id),
                   (SELECT r.role_name FROM user_roles ur
                    JOIN roles r ON r.role_id = ur.role_id
                    WHERE ur.user_id = u.user_id LIMIT 1)
            FROM notification_log t
            JOIN users u            ON u.user_id     = t.user_id
            LEFT JOIN locations pl  ON pl.location_id = u.location_id
            WHERE t.notif_id = %s AND t.type = 'support'
        """, [ticket_id])
        t = cur.fetchone()

        if not t:
            return JsonResponse({'error': 'Ticket not found'}, status=404)

        cur.execute("""
            SELECT notif_id, body, type, created_at, is_read
            FROM notification_log
            WHERE notif_id = %s OR ref_id = %s
            ORDER BY created_at ASC
        """, [ticket_id, ticket_id])
        msgs = cur.fetchall()

    messages_list = []
    for m in msgs:
        is_admin = (m[2] == 'support_reply')
        messages_list.append({
            'id': m[0], 'body': m[1], 'is_admin_reply': is_admin,
            'author_name': 'Pack-N-Ship System' if is_admin else f"{t[6] or ''} {t[7] or ''}".strip(),
            'created_at': m[3].isoformat() if m[3] else None,
            'is_read': m[4],
        })

    return JsonResponse({
        'ticket': {
            'id': t[0], 'subject': t[2], 'is_read': t[3],
            'created_at': t[4].isoformat() if t[4] else None,
        },
        'user': {
            'user_id': t[1],
            'name': f"{t[6] or ''} {t[7] or ''}".strip() or f"USR-{t[1]}",
            'email': t[8] or '—', 'phone': t[9] or '—',
            'joined': t[10].strftime('%b %Y') if t[10] else '—',
            'address': ', '.join(filter(None, [t[11], t[12], t[13], t[14]])) or '—',
            'wallet': float(t[15] or 0), 'total_deliveries': int(t[16] or 0),
            'avg_rating': float(t[17]) if t[17] else 0,
            'role': (t[18] or 'Sender').title(),
        },
        'messages': messages_list,
    })


@admin_required
@require_POST
def support_reply_api(request, ticket_id):
    try:
        body = (json.loads(request.body).get('message') or '').strip()
    except Exception:
        body = ''

    if not body:
        return JsonResponse({'error': 'Empty message'}, status=400)

    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id FROM notification_log
            WHERE notif_id = %s AND type = 'support'
        """, [ticket_id])
        row = cur.fetchone()
        if not row:
            return JsonResponse({'error': 'Ticket not found'}, status=404)

        user_id = row[0]

        cur.execute("""
            INSERT INTO notification_log (user_id, title, body, type, is_read, ref_id)
            VALUES (%s, 'Pack-N-Ship System', %s, 'support_reply', FALSE, %s)
            RETURNING notif_id, created_at
        """, [user_id, body, ticket_id])
        msg_id, created_at = cur.fetchone()

        cur.execute("UPDATE notification_log SET is_read = TRUE WHERE notif_id = %s", [ticket_id])

    return JsonResponse({
        'message': {
            'id': msg_id, 'body': body, 'is_admin_reply': True,
            'author_name': 'Pack-N-Ship System',
            'created_at': created_at.isoformat(),
        }
    })


@admin_required
@require_POST
def support_status_api(request, ticket_id):
    try:
        status = (json.loads(request.body).get('status') or '').strip()
    except Exception:
        status = ''

    if status not in ('open', 'pending', 'resolved'):
        return JsonResponse({'error': 'Invalid status'}, status=400)

    with connection.cursor() as cur:
        resolved = (status == 'resolved')
        cur.execute("""
            UPDATE notification_log SET is_read = %s
            WHERE notif_id = %s AND type = 'support'
        """, [resolved, ticket_id])

    return JsonResponse({'status': 'success', 'new_status': status})


# ==========================================
# DIRECT CHAT (users.html modal)
# ==========================================
def _admin_user_id():
    with connection.cursor() as cur:
        # 1. Match your admin@packnship.com account (user_id = 1)
        cur.execute("""
            SELECT user_id, first_name, last_name FROM users
            WHERE LOWER(email) = LOWER(%s)
            LIMIT 1
        """, [ADMIN_EMAIL])
        row = cur.fetchone()
        if row:
            if row[1] != 'Pack-N-Ship' or row[2] != 'System':
                cur.execute("""
                    UPDATE users
                    SET first_name = 'Pack-N-Ship', last_name = 'System'
                    WHERE user_id = %s
                """, [row[0]])
            return row[0]

        # 2. Fallback to role = admin
        cur.execute("""
            SELECT u.user_id FROM users u
            JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN roles r ON r.role_id = ur.role_id
            WHERE r.role_name ILIKE 'admin'
            ORDER BY u.user_id LIMIT 1
        """)
        row = cur.fetchone()
        return row[0] if row else 1


@admin_required
@require_POST
def chat_start_room_api(request):
    try:
        payload = json.loads(request.body)
    except Exception:
        payload = {}

    target_user_id = payload.get('user_id')
    if not target_user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    admin_id = _admin_user_id()
    if not admin_id:
        return JsonResponse({'error': 'Admin user not found'}, status=500)

    if int(target_user_id) == int(admin_id):
        return JsonResponse({'error': 'Cannot chat with yourself'}, status=400)

    with connection.cursor() as cur:
        cur.execute("""
            SELECT room_id FROM chat_rooms
            WHERE is_support = TRUE
              AND ((participant_a = %s AND participant_b = %s)
                OR (participant_a = %s AND participant_b = %s))
            LIMIT 1
        """, [admin_id, target_user_id, target_user_id, admin_id])
        existing = cur.fetchone()
        if existing:
            room_id = existing[0]
            created = False
        else:
            cur.execute("""
                INSERT INTO chat_rooms (delivery_id, is_support, participant_a, participant_b)
                VALUES (NULL, TRUE, %s, %s)
                RETURNING room_id
            """, [admin_id, target_user_id])
            room_id = cur.fetchone()[0]
            created = True

        # Ensure the chat room is unarchived & undeleted for the mobile user
        cur.execute("""
            INSERT INTO chat_room_states (room_id, user_id, is_archived, is_deleted)
            VALUES (%s, %s, FALSE, FALSE)
            ON CONFLICT (room_id, user_id)
            DO UPDATE SET is_archived = FALSE, is_deleted = FALSE
        """, [room_id, target_user_id])

    return JsonResponse({'status': 'success', 'room_id': room_id, 'created': created})


@admin_required
@require_http_methods(["GET"])
def chat_thread_api(request, room_id):
    admin_id = _admin_user_id()

    with connection.cursor() as cur:
        cur.execute("""
            SELECT r.room_id, r.participant_a, r.participant_b,
                   ua.first_name, ua.last_name,
                   ub.first_name, ub.last_name
            FROM chat_rooms r
            LEFT JOIN users ua ON ua.user_id = r.participant_a
            LEFT JOIN users ub ON ub.user_id = r.participant_b
            WHERE r.room_id = %s AND r.is_support = TRUE
        """, [room_id])
        r = cur.fetchone()
        if not r:
            return JsonResponse({'error': 'Room not found'}, status=404)

        cur.execute("""
            SELECT m.message_id, m.sender_id, m.message, m.sent_at, m.is_read
            FROM chat_messages m
            WHERE m.room_id = %s
            ORDER BY m.sent_at ASC
        """, [room_id])
        msgs = cur.fetchall()

        if admin_id:
            cur.execute("""
                UPDATE chat_messages SET is_read = TRUE
                WHERE room_id = %s AND sender_id <> %s AND is_read = FALSE
            """, [room_id, admin_id])

    return JsonResponse({
        'room_id': r[0],
        'participant_a': r[1], 'participant_b': r[2],
        'participant_a_name': f"{r[3] or ''} {r[4] or ''}".strip(),
        'participant_b_name': f"{r[5] or ''} {r[6] or ''}".strip(),
        'admin_id': admin_id,
        'messages': [{
            'id': m[0], 'sender_id': m[1], 'message': m[2],
            'sent_at': m[3].isoformat() if m[3] else None,
            'is_read': m[4], 'is_admin': m[1] == admin_id,
        } for m in msgs],
    })


@admin_required
@require_POST
def chat_send_api(request, room_id):
    try:
        body = (json.loads(request.body).get('message') or '').strip()
    except Exception:
        body = ''

    if not body:
        return JsonResponse({'error': 'Empty message'}, status=400)

    admin_id = _admin_user_id()
    if not admin_id:
        return JsonResponse({'error': 'Admin not found'}, status=500)

    with connection.cursor() as cur:
        cur.execute("SELECT room_id FROM chat_rooms WHERE room_id = %s AND is_support = TRUE", [room_id])
        if not cur.fetchone():
            return JsonResponse({'error': 'Room not found'}, status=404)

        cur.execute("""
            INSERT INTO chat_messages (room_id, sender_id, message)
            VALUES (%s, %s, %s)
            RETURNING message_id, sent_at
        """, [room_id, admin_id, body])
        msg_id, sent_at = cur.fetchone()

        cur.execute("""
            SELECT CASE WHEN participant_a = %s THEN participant_b ELSE participant_a END
            FROM chat_rooms WHERE room_id = %s
        """, [admin_id, room_id])
        row = cur.fetchone()
        if row and row[0]:
            target_user = row[0]

            # Ensure room is active in user's mobile inbox
            cur.execute("""
                INSERT INTO chat_room_states (room_id, user_id, is_archived, is_deleted)
                VALUES (%s, %s, FALSE, FALSE)
                ON CONFLICT (room_id, user_id)
                DO UPDATE SET is_archived = FALSE, is_deleted = FALSE
            """, [room_id, target_user])

            # Insert notification with Pack-N-Ship System title
            cur.execute("""
                INSERT INTO notification_log (user_id, title, body, type, ref_id)
                VALUES (%s, 'Pack-N-Ship System', %s, 'chat', %s)
            """, [target_user, body[:140], room_id])

    return JsonResponse({'message': {
        'id': msg_id, 'sender_id': admin_id, 'message': body,
        'sent_at': sent_at.isoformat(), 'is_read': False, 'is_admin': True,
    }})