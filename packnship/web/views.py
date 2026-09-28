from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import ProviderVerification
from django.contrib import messages
from django.db import connection
from django.template.exceptions import TemplateDoesNotExist
import json


# ==========================================
# MOCK DATA FOR MESSAGES INBOX
# ==========================================
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
        u = request.POST.get('username')
        p = request.POST.get('password')

        if u == 'admin' and p == 'admin':
            request.session['is_mock_logged_in'] = True
            return redirect('dashboard')
        else:
            error_message = "Invalid credentials. Please use admin / admin."

    return render(request, 'pages/login.html', {'error_message': error_message})


def dashboard(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    stats = {
        'total_users': 0,
        'total_deliveries': 0,
        'total_revenue': 0.0,
        'pending_deliveries': 0,
    }
    # Percent deltas vs "yesterday" (real: yesterday vs today; here: last 7d vs prior 7d)
    deltas = {
        'users': 0.0,
        'deliveries': 0.0,
        'revenue': 0.0,
        'pending': 0.0,
    }
    chart_labels = []
    chart_values = []

    try:
        with connection.cursor() as cursor:
            # ---- Top-line stats ----
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM deliveries) AS total_deliveries,
                    (SELECT COALESCE(SUM(total_amount), 0)
                       FROM transactions
                      WHERE status IN ('Completed', 'Released')) AS total_revenue,
                    (SELECT COUNT(*)
                       FROM (
                         SELECT DISTINCT ON (delivery_id) delivery_id, status
                         FROM delivery_status_history
                         ORDER BY delivery_id, updated_at DESC
                       ) latest
                      WHERE latest.status = 'Pending') AS pending_deliveries
            """)
            row = cursor.fetchone()
            if row:
                stats['total_users']        = int(row[0] or 0)
                stats['total_deliveries']   = int(row[1] or 0)
                stats['total_revenue']      = float(row[2] or 0)
                stats['pending_deliveries'] = int(row[3] or 0)

            # ---- 7-day deltas (today vs yesterday, this week vs last week) ----
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE)               AS users_today,
                    COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE - INTERVAL '1 day') AS users_yest
                FROM users
            """)
            r = cursor.fetchone()
            if r and r[1]:
                deltas['users'] = ((r[0] - r[1]) / float(r[1])) * 100

            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE accepted_at::date = CURRENT_DATE)                AS del_today,
                    COUNT(*) FILTER (WHERE accepted_at::date = CURRENT_DATE - INTERVAL '1 day') AS del_yest
                FROM deliveries
            """)
            r = cursor.fetchone()
            if r and r[1]:
                deltas['deliveries'] = ((r[0] - r[1]) / float(r[1])) * 100

            cursor.execute("""
                SELECT
                    COALESCE(SUM(total_amount) FILTER (WHERE processed_at::date = CURRENT_DATE), 0)                AS rev_today,
                    COALESCE(SUM(total_amount) FILTER (WHERE processed_at::date = CURRENT_DATE - INTERVAL '1 day'), 0) AS rev_yest
                FROM transactions
                WHERE status IN ('Completed', 'Released')
            """)
            r = cursor.fetchone()
            if r and float(r[1] or 0) > 0:
                deltas['revenue'] = ((float(r[0]) - float(r[1])) / float(r[1])) * 100

            # ---- Revenue chart: last 12 months of released transactions ----
            cursor.execute("""
                SELECT
                    TO_CHAR(DATE_TRUNC('month', processed_at), 'Mon YYYY') AS month_label,
                    COALESCE(SUM(total_amount), 0) AS month_total
                FROM transactions
                WHERE status IN ('Completed', 'Released')
                  AND processed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months'
                GROUP BY DATE_TRUNC('month', processed_at)
                ORDER BY DATE_TRUNC('month', processed_at)
            """)
            for m_label, m_total in cursor.fetchall():
                chart_labels.append(m_label)
                chart_values.append(float(m_total or 0))

    except Exception as e:
        print(f"[dashboard] DB error: {e}")

    context = {
        'stats': stats,
        'deltas': deltas,
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'total_revenue_display': f"₱{stats['total_revenue']:,.2f}",
    }
    return render(request, 'pages/dashboard.html', context)


def users_page(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab = request.GET.get('tab', 'all')

    providers = []
    senders = []

    try:
        with connection.cursor() as cursor:

            # ============================================================
            # PROVIDERS  (tab = all / verified / pending)
            # ============================================================
            if current_tab in ('all', 'verified', 'pending'):
                cursor.execute("""
                    SELECT
                        u.user_id,
                        u.first_name,
                        u.middle_name,
                        u.last_name,
                        u.email,
                        u.phone_number,
                        u.is_verified,
                        u.is_active,
                        u.created_at,
                        pl.street_address AS p_street,
                        pl.barangay       AS p_barangay,
                        pl.city           AS p_city,
                        pl.province       AS p_province,
                        v.vehicle_type,
                        v.plate_number,
                        pv.verification_status AS provider_verif_status,
                        pw.balance AS wallet_balance,
                        COALESCE(stats.total_deliveries, 0)  AS total_deliveries,
                        COALESCE(stats.completed, 0)         AS completed,
                        COALESCE(stats.cancelled, 0)         AS cancelled,
                        COALESCE(stats.active_deliveries, 0) AS active_deliveries,
                        COALESCE(stats.total_earnings, 0)    AS total_earnings,
                        COALESCE(rating.avg_rating, 0)       AS avg_rating,
                        COALESCE(issues.dispute_count, 0)    AS dispute_count
                    FROM users u
                    JOIN user_roles ur ON ur.user_id = u.user_id
                    JOIN roles r       ON r.role_id   = ur.role_id
                    LEFT JOIN locations pl ON pl.location_id = u.primary_loc_id
                    LEFT JOIN vehicles  v  ON v.provider_id  = u.user_id
                    LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                    LEFT JOIN provider_wallet pw ON pw.provider_id = u.user_id
                    LEFT JOIN (
                        SELECT
                            d.provider_id,
                            COUNT(*) AS total_deliveries,
                            COUNT(*) FILTER (WHERE dsh_latest.status = 'Completed') AS completed,
                            COUNT(*) FILTER (WHERE dsh_latest.status = 'Cancelled') AS cancelled,
                            COUNT(*) FILTER (WHERE dsh_latest.status IN ('Pending', 'Accepted', 'In Transit')) AS active_deliveries,
                            COALESCE(SUM(ep.amount) FILTER (WHERE ep.escrow_status = 'Released'), 0) AS total_earnings
                        FROM deliveries d
                        LEFT JOIN LATERAL (
                            SELECT status FROM delivery_status_history
                            WHERE delivery_id = d.delivery_id
                            ORDER BY updated_at DESC LIMIT 1
                        ) dsh_latest ON true
                        LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                        GROUP BY d.provider_id
                    ) stats ON stats.provider_id = u.user_id
                    LEFT JOIN (
                        SELECT reviewee_id,
                               ROUND(AVG(rating)::numeric, 1) AS avg_rating
                        FROM ratings_reviews
                        GROUP BY reviewee_id
                    ) rating ON rating.reviewee_id = u.user_id
                    LEFT JOIN (
                        SELECT reported_by, COUNT(*) AS dispute_count
                        FROM delivery_issues
                        GROUP BY reported_by
                    ) issues ON issues.reported_by = u.user_id
                    WHERE r.role_name ILIKE 'provider'
                    ORDER BY u.created_at DESC
                """)

                for row in cursor.fetchall():
                    (user_id, first_name, middle_name, last_name, email, phone,
                     is_verified, is_active, created_at,
                     p_street, p_barangay, p_city, p_province,
                     vehicle_type, plate_number,
                     provider_verif_status,
                     wallet_balance,
                     total_deliveries, completed, cancelled, active_deliveries,
                     total_earnings, avg_rating, dispute_count) = row

                    full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{user_id}"

                    addr_primary = ", ".join(filter(None, [p_street, p_barangay, p_city, p_province])) or '—'
                    addr_other = '—'

                    vehicle_display = (
                        f"{vehicle_type} · {plate_number}"
                        if vehicle_type and plate_number else '—'
                    )

                    if (provider_verif_status or '').lower() in ('approved', 'verified'):
                        status1 = 'Verified'
                    elif provider_verif_status:
                        status1 = provider_verif_status
                    elif is_verified:
                        status1 = 'Verified'
                    else:
                        status1 = 'Pending'

                    status2 = 'Active' if is_active else 'Inactive'

                    cursor.execute("""
                        SELECT
                            d.delivery_id,
                            COALESCE(d.completed_at, d.accepted_at) AS ts,
                            COALESCE(dsh.status, 'Pending')         AS status,
                            COALESCE(ep.amount, 0)                  AS amount
                        FROM deliveries d
                        LEFT JOIN LATERAL (
                            SELECT status FROM delivery_status_history
                            WHERE delivery_id = d.delivery_id
                            ORDER BY updated_at DESC LIMIT 1
                        ) dsh ON true
                        LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                        WHERE d.provider_id = %s
                        ORDER BY d.accepted_at DESC
                        LIMIT 3
                    """, [user_id])

                    recent_list = []
                    for (did, ts, dstat, amt) in cursor.fetchall():
                        date_str = ts.strftime('%b %d, %Y') if ts else '—'
                        recent_list.append(f"{did}|{date_str}|{dstat}|₱{float(amt or 0):,.2f}")
                    recent_str = ";".join(recent_list) if recent_list else ''

                    providers.append({
                        'id': f"USI{user_id}",
                        'raw_id': user_id,
                        'name': full_name,
                        'email': email or '—',
                        'phone': phone or '—',
                        'role': 'Provider',
                        'status1': status1,
                        'status2': status2,
                        'addr_primary': addr_primary,
                        'addr_other': addr_other,
                        'vehicle': vehicle_display,
                        'total_deliveries': total_deliveries or 0,
                        'completed': completed or 0,
                        'cancelled': cancelled or 0,
                        'active_deliveries': active_deliveries or 0,
                        'total_earnings': f"₱{float(total_earnings or 0):,.2f}",
                        'wallet_balance': f"₱{float(wallet_balance or 0):,.2f}",
                        'avg_rating_received': f"{float(avg_rating):.1f}" if avg_rating else '—',
                        'disputes_filed': dispute_count or 0,
                        'recent_deliveries': recent_str,
                        'is_verified': bool(is_verified),
                        'joined_at': created_at.strftime('%b %d, %Y') if created_at else '—',
                    })

                if current_tab == 'verified':
                    providers = [p for p in providers if p['status1'] == 'Verified']
                elif current_tab == 'pending':
                    providers = [p for p in providers if p['status1'] == 'Pending']

            # ============================================================
            # SENDERS  (tab = senders)
            # ============================================================
            if current_tab == 'senders':
                cursor.execute("""
                    SELECT
                        u.user_id,
                        u.first_name,
                        u.middle_name,
                        u.last_name,
                        u.email,
                        u.phone_number,
                        u.is_verified,
                        u.is_active,
                        u.created_at,
                        pl.street_address AS p_street,
                        pl.barangay       AS p_barangay,
                        pl.city           AS p_city,
                        pl.province       AS p_province,
                        COALESCE(stats.total_requests, 0) AS total_requests,
                        COALESCE(stats.completed, 0)      AS completed,
                        COALESCE(stats.cancelled, 0)      AS cancelled,
                        COALESCE(stats.active_requests, 0) AS active_requests,
                        COALESCE(stats.total_spent, 0)    AS total_spent,
                        COALESCE(rating.avg_rating, 0)    AS avg_rating,
                        COALESCE(issues.dispute_count, 0) AS dispute_count,
                        COALESCE(recv.saved_receivers, 0) AS saved_receivers
                    FROM users u
                    JOIN user_roles ur ON ur.user_id = u.user_id
                    JOIN roles r       ON r.role_id   = ur.role_id
                    LEFT JOIN locations pl ON pl.location_id = u.primary_loc_id
                    LEFT JOIN (
                        SELECT
                            dr.sender_id,
                            COUNT(*) AS total_requests,
                            COUNT(*) FILTER (WHERE dr.delivery_status = 'Completed') AS completed,
                            COUNT(*) FILTER (WHERE dr.delivery_status = 'Cancelled') AS cancelled,
                            COUNT(*) FILTER (WHERE dr.delivery_status IN ('Pending','Accepted','In Transit')) AS active_requests,
                            COALESCE(SUM(ep.amount) FILTER (WHERE ep.escrow_status = 'Released'), 0) AS total_spent
                        FROM delivery_requests dr
                        LEFT JOIN deliveries d       ON d.request_id = dr.request_id
                        LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                        GROUP BY dr.sender_id
                    ) stats ON stats.sender_id = u.user_id
                    LEFT JOIN (
                        SELECT reviewer_id,
                               ROUND(AVG(rating)::numeric, 1) AS avg_rating
                        FROM ratings_reviews
                        GROUP BY reviewer_id
                    ) rating ON rating.reviewer_id = u.user_id
                    LEFT JOIN (
                        SELECT reported_by, COUNT(*) AS dispute_count
                        FROM delivery_issues
                        GROUP BY reported_by
                    ) issues ON issues.reported_by = u.user_id
                    LEFT JOIN (
                        SELECT sender_id, COUNT(*) AS saved_receivers
                        FROM receivers
                        GROUP BY sender_id
                    ) recv ON recv.sender_id = u.user_id
                    WHERE r.role_name ILIKE 'sender'
                    ORDER BY u.created_at DESC
                """)

                for row in cursor.fetchall():
                    (user_id, first_name, middle_name, last_name, email, phone,
                     is_verified, is_active, created_at,
                     p_street, p_barangay, p_city, p_province,
                     total_requests, completed, cancelled, active_requests,
                     total_spent, avg_rating, dispute_count, saved_receivers) = row

                    full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{user_id}"
                    addr_primary = ", ".join(filter(None, [p_street, p_barangay, p_city, p_province])) or '—'

                    cursor.execute("""
                        SELECT request_id, created_at, delivery_status, estimated_cost
                        FROM delivery_requests
                        WHERE sender_id = %s
                        ORDER BY created_at DESC
                        LIMIT 3
                    """, [user_id])

                    recent_list = []
                    for (rid, ts, rstat, cost) in cursor.fetchall():
                        date_str = ts.strftime('%b %d, %Y') if ts else '—'
                        recent_list.append(f"{rid}|{date_str}|{rstat}|₱{float(cost or 0):,.2f}")
                    recent_str = ";".join(recent_list) if recent_list else ''

                    senders.append({
                        'id': f"SDI{user_id}",
                        'raw_id': user_id,
                        'name': full_name,
                        'email': email or '—',
                        'phone': phone or '—',
                        'role': 'Sender',
                        'status2': 'Active' if is_active else 'Inactive',
                        'addr_primary': addr_primary,
                        'addr_other': '—',
                        'is_verified': bool(is_verified),
                        'joined_at': created_at.strftime('%b %d, %Y') if created_at else '—',
                        'total_requests': total_requests or 0,
                        'completed': completed or 0,
                        'cancelled': cancelled or 0,
                        'active_requests': active_requests or 0,
                        'total_spent': f"₱{float(total_spent or 0):,.2f}",
                        'avg_rating_received': f"{float(avg_rating):.1f}" if avg_rating else '—',
                        'disputes_filed': dispute_count or 0,
                        'saved_receivers': saved_receivers or 0,
                        'recent_requests': recent_str,
                    })

    except Exception as e:
        # Surface the error in the console for debugging; keep the page alive
        print(f"[users_page] DB error: {e}")

    return render(request, 'pages/users.html', {
        'users': providers,
        'senders': senders,
        'current_tab': current_tab,
    })


def provider_verification(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab = request.GET.get('tab', 'pending')
    verifications = []

    try:
        with connection.cursor() as cursor:
            if current_tab == 'rejected':
                status_filter = ['Rejected']
            else:
                status_filter = ['Pending']

            cursor.execute("""
                SELECT
                    pv.verification_id,
                    pv.drivers_license_number,
                    pv.license_expiry_date,
                    pv.selfie_photo,
                    pv.selfie_photo_back,
                    pv.id_analyzer_decision,
                    pv.id_analyzer_confidence,
                    pv.id_analyzer_raw,
                    COALESCE(pv.verification_status, 'Pending') AS verification_status,
                    pv.submitted_at,
                    pv.bc_verif_tx_hash,
                    u.user_id,
                    u.first_name,
                    u.middle_name,
                    u.last_name,
                    u.email,
                    u.phone_number,
                    u.id_photo,
                    u.valid_id_type,
                    u.valid_id_number,
                    v.vehicle_type,
                    v.plate_number,
                    v.vehicle_doc,
                    v.verification_status AS vehicle_verif_status
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.user_id
                JOIN roles r       ON r.role_id   = ur.role_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                LEFT JOIN vehicles v ON v.provider_id = u.user_id
                WHERE r.role_name ILIKE 'provider'
                  AND COALESCE(pv.verification_status, 'Pending') = ANY(%s)
                ORDER BY COALESCE(pv.submitted_at, u.created_at) DESC
            """, [status_filter])

            rows = cursor.fetchall()

            for row in rows:
                (verification_id, license_no, expiry_date, selfie_photo, selfie_photo_back,
                 id_analyzer_decision, id_analyzer_confidence, id_analyzer_raw,
                 verif_status, submitted_at, tx_hash,
                 uid, first_name, middle_name, last_name, email, phone,
                 id_photo, valid_id_type, valid_id_number,
                 vehicle_type, plate_number, vehicle_doc, vehicle_verif_status) = row

                full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{uid}"

                verifications.append({
                    'verification_id': verification_id or 0,
                    'user_id': uid,
                    'name': full_name,
                    'email': email or '—',
                    'phone': phone or '—',
                    'license_no': license_no or '—',
                    'license_expiry': expiry_date.strftime('%Y-%m-%d') if expiry_date else '—',
                    'selfie_photo': selfie_photo or '',
                    'selfie_photo_back': selfie_photo_back or '',
                    'id_analyzer_decision': id_analyzer_decision or '',
                    'id_analyzer_confidence': float(id_analyzer_confidence) if id_analyzer_confidence is not None else None,
                    'id_analyzer_raw': id_analyzer_raw or {},
                    'id_photo': id_photo or '',
                    'valid_id_type': valid_id_type or '—',
                    'valid_id_number': valid_id_number or '—',
                    'vehicle_type': vehicle_type or '—',
                    'plate_no': plate_number or '—',
                    'vehicle_doc': vehicle_doc or '',
                    'vehicle_verif_status': vehicle_verif_status or 'Pending',
                    'status': verif_status or 'Pending',
                    'submitted_at': submitted_at.strftime('%b %d, %Y %I:%M %p') if submitted_at else '—',
                    'bc_verif_tx_hash': tx_hash or '',
                })

    except Exception as e:
        print(f"[provider_verification] DB error: {e}")

    return render(request, 'pages/provider_verification.html', {
        'verifications': verifications,
        'current_tab': current_tab,
    })


def approve_provider(request, user_id):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT verification_id FROM provider_verifications
                    WHERE provider_id = %s
                    ORDER BY submitted_at DESC
                    LIMIT 1
                """, [user_id])
                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE provider_verifications
                        SET verification_status = 'Approved',
                            verified_at = NOW()
                        WHERE provider_id = %s
                    """, [user_id])
                    print(f"[approve_provider] UPDATED user_id={user_id}")
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, verified_at, provider_id)
                        VALUES (%s, NOW()::date, 'N/A', 'Approved', NOW(), %s)
                    """, [placeholder_license, user_id])
                    print(f"[approve_provider] INSERTED user_id={user_id}")

                cursor.execute("""
                    UPDATE users SET is_verified = TRUE WHERE user_id = %s
                """, [user_id])

            messages.success(request, f'Provider (US{user_id}) approved successfully.')
        except Exception as e:
            print(f"[approve_provider] DB error: {e}")
            messages.error(request, f'Failed to approve provider: {e}')

    return redirect('provider_verification')


def reject_provider(request, user_id):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT verification_id FROM provider_verifications
                    WHERE provider_id = %s
                    ORDER BY submitted_at DESC
                    LIMIT 1
                """, [user_id])
                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE provider_verifications
                        SET verification_status = 'Rejected'
                        WHERE provider_id = %s
                    """, [user_id])
                    print(f"[reject_provider] UPDATED user_id={user_id}")
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, provider_id)
                        VALUES (%s, NOW()::date, 'N/A', 'Rejected', %s)
                    """, [placeholder_license, user_id])
                    print(f"[reject_provider] INSERTED user_id={user_id}")

                cursor.execute("""
                    UPDATE users SET is_verified = FALSE WHERE user_id = %s
                """, [user_id])

            messages.success(request, f'Provider (US{user_id}) rejected.')
        except Exception as e:
            print(f"[reject_provider] DB error: {e}")
            messages.error(request, f'Failed to reject provider: {e}')

    return redirect('provider_verification')

def vehicle_verification(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab = request.GET.get('tab', 'pending')
    vehicles = []

    try:
        with connection.cursor() as cursor:
            if current_tab == 'verified':
                status_filter = ['Verified']
            elif current_tab == 'rejected':
                status_filter = ['Rejected']
            else:
                status_filter = ['Pending']

            cursor.execute("""
                SELECT
                    v.vehicle_id,
                    v.vehicle_type,
                    v.plate_number,
                    v.max_volume_liters,
                    v.max_weight_kg,
                    v.cargo_length_cm,
                    v.cargo_width_cm,
                    v.cargo_height_cm,
                    v.vehicle_doc,
                    COALESCE(v.verification_status, 'Pending') AS verification_status,
                    v.provider_id,
                    u.first_name,
                    u.middle_name,
                    u.last_name,
                    u.email,
                    u.phone_number,
                    pv.verification_status AS provider_verif_status
                FROM vehicles v
                JOIN users u ON u.user_id = v.provider_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                WHERE COALESCE(v.verification_status, 'Pending') = ANY(%s)
                ORDER BY v.vehicle_id DESC
            """, [status_filter])

            rows = cursor.fetchall()

            for row in rows:
                (vehicle_id, vehicle_type, plate_number,
                 max_volume, max_weight,
                 cargo_length, cargo_width, cargo_height,
                 vehicle_doc, verif_status, provider_id,
                 first_name, middle_name, last_name, email, phone,
                 provider_verif_status) = row

                full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{provider_id}"

                vehicles.append({
                    'vehicle_id': vehicle_id,
                    'vehicle_type': vehicle_type or '—',
                    'plate_number': plate_number or '—',
                    'max_volume_liters': float(max_volume) if max_volume is not None else 0,
                    'max_weight_kg': float(max_weight) if max_weight is not None else 0,
                    'cargo_length_cm': float(cargo_length) if cargo_length is not None else 0,
                    'cargo_width_cm': float(cargo_width) if cargo_width is not None else 0,
                    'cargo_height_cm': float(cargo_height) if cargo_height is not None else 0,
                    'vehicle_doc': vehicle_doc or '',
                    'status': verif_status or 'Pending',
                    'provider_id': provider_id,
                    'provider_name': full_name,
                    'provider_email': email or '—',
                    'provider_phone': phone or '—',
                    'provider_verif_status': provider_verif_status or 'Pending',
                })

    except Exception as e:
        print(f"[vehicle_verification] DB error: {e}")

    return render(request, 'pages/vehicle_verification.html', {
        'vehicles': vehicles,
        'current_tab': current_tab,
    })


def approve_vehicle(request, vehicle_id):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE vehicles
                    SET verification_status = 'Verified'
                    WHERE vehicle_id = %s
                """, [vehicle_id])

            messages.success(request, f'Vehicle #{vehicle_id} approved successfully.')
        except Exception as e:
            print(f"[approve_vehicle] DB error: {e}")
            messages.error(request, f'Failed to approve vehicle: {e}')

    return redirect('vehicle_verification')


def reject_vehicle(request, vehicle_id):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE vehicles
                    SET verification_status = 'Rejected'
                    WHERE vehicle_id = %s
                """, [vehicle_id])

            messages.success(request, f'Vehicle #{vehicle_id} rejected.')
        except Exception as e:
            print(f"[reject_vehicle] DB error: {e}")
            messages.error(request, f'Failed to reject vehicle: {e}')

    return redirect('vehicle_verification')

def deliveries(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    delivery_list = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    d.delivery_id,
                    d.accepted_at,
                    d.estimated_eta,
                    d.completed_at,

                    -- Sender
                    s.user_id        AS sender_id,
                    s.first_name     AS s_first,
                    s.middle_name    AS s_middle,
                    s.last_name      AS s_last,
                    s.phone_number   AS sender_phone,

                    -- Provider
                    p.user_id        AS provider_id,
                    p.first_name     AS p_first,
                    p.middle_name    AS p_middle,
                    p.last_name      AS p_last,
                    v.vehicle_type,
                    v.plate_number,

                    -- Locations
                    pl.street_address AS pickup_street,
                    pl.barangay       AS pickup_brgy,
                    pl.city           AS pickup_city,
                    pl.province       AS pickup_prov,
                    pl.latitude       AS pickup_lat,
                    pl.longitude      AS pickup_lng,

                    dl.street_address AS dropoff_street,
                    dl.barangay       AS dropoff_brgy,
                    dl.city           AS dropoff_city,
                    dl.province       AS dropoff_prov,
                    dl.latitude       AS dropoff_lat,
                    dl.longitude      AS dropoff_lng,

                    -- Delivery request
                    dr.pickup_type,
                    dr.delivery_status,
                    dr.emergency_flag,
                    dr.total_distance,
                    dr.estimated_cost,
                    dr.created_at     AS requested_at,
                    dr.receiver_phone,

                    -- Cargo
                    cp.description      AS cargo_description,
                    cp.cargo_pic        AS cargo_photo,
                    cp.total_weight_kg,
                    cp.cargo_length_cm,
                    cp.cargo_width_cm,
                    cp.cargo_height_cm,
                    cp.small_box_qty,
                    cp.medium_box_qty,
                    cp.large_box_qty,
                    cp.is_fragile,

                    -- Latest status from history (authoritative)
                    dsh.status AS latest_status,
                    dsh.updated_at AS latest_status_at,

                    -- Escrow
                    ep.escrow_id,
                    ep.amount            AS escrow_amount,
                    ep.escrow_status,
                    ep.emergency_frozen,
                    ep.bc_escrow_tx_hash,

                    -- Transaction (fees)
                    t.base_amount,
                    t.service_fee,
                    t.penalty_fee,
                    t.total_amount,
                    t.payment_method,
                    t.status             AS payment_status,
                    t.processed_at,

                    -- Chat room
                    cr.room_id,

                    -- QR verification
                    qr.pickup_verified,
                    qr.dropoff_verified

                FROM deliveries d
                JOIN delivery_requests dr ON dr.request_id = d.request_id
                JOIN users s              ON s.user_id     = dr.sender_id
                JOIN users p              ON p.user_id     = d.provider_id
                JOIN vehicles v           ON v.vehicle_id  = d.vehicle_id
                LEFT JOIN locations pl    ON pl.location_id = dr.pickup_location_id
                LEFT JOIN locations dl    ON dl.location_id = dr.dropoff_location_id
                LEFT JOIN cargo_profiles cp ON cp.cargo_id  = dr.cargo_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t     ON t.escrow_id    = ep.escrow_id
                LEFT JOIN chat_rooms cr      ON cr.delivery_id = d.delivery_id
                LEFT JOIN qr_verifications qr ON qr.delivery_id = d.delivery_id
                LEFT JOIN LATERAL (
                    SELECT status, updated_at
                    FROM delivery_status_history
                    WHERE delivery_id = d.delivery_id
                    ORDER BY updated_at DESC
                    LIMIT 1
                ) dsh ON true
                ORDER BY d.accepted_at DESC
            """)

            rows = cursor.fetchall()

            for row in rows:
                (delivery_id, accepted_at, eta, completed_at,
                 s_id, s_first, s_middle, s_last, sender_phone,
                 p_id, p_first, p_middle, p_last, vehicle_type, plate_number,
                 pu_street, pu_brgy, pu_city, pu_prov, pu_lat, pu_lng,
                 do_street, do_brgy, do_city, do_prov, do_lat, do_lng,
                 pickup_type, delivery_status, emergency_flag, total_distance, estimated_cost, requested_at, receiver_phone,
                 cargo_desc, cargo_pic, weight, cl, cw, ch, sb, mb, lb, fragile,
                 latest_status, latest_status_at,
                 escrow_id, escrow_amount, escrow_status, emergency_frozen, bc_escrow_tx,
                 base_amount, service_fee, penalty_fee, total_amount, payment_method, payment_status, processed_at,
                 room_id, pickup_verified, dropoff_verified) = row

                sender_name   = " ".join(filter(None, [s_first, s_middle, s_last])) or f"USR-{s_id}"
                provider_name = " ".join(filter(None, [p_first, p_middle, p_last])) or f"PRV-{p_id}"

                pickup_addr  = ", ".join(filter(None, [pu_street, pu_brgy, pu_city, pu_prov])) or '—'
                dropoff_addr = ", ".join(filter(None, [do_street, do_brgy, do_city, do_prov])) or '—'

                # Authoritative status: prefer latest history, fall back to delivery_requests.delivery_status
                status = latest_status or delivery_status or 'Pending'

                # Pull the full status history for the timeline
                cursor.execute("""
                    SELECT status, updated_at
                    FROM delivery_status_history
                    WHERE delivery_id = %s
                    ORDER BY updated_at ASC
                """, [delivery_id])
                history_rows = cursor.fetchall()
                status_history_str = ";".join(
                    f"{st}|{ts.strftime('%b %d, %Y — %I:%M %p') if ts else '—'}"
                    for st, ts in history_rows
                )

                # Active emergency?
                cursor.execute("""
                    SELECT issue_type, description, status
                    FROM delivery_issues
                    WHERE delivery_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, [delivery_id])
                issue = cursor.fetchone()

                emergency_display = 'None'
                emergency_type = ''
                emergency_status = ''
                if emergency_flag and issue:
                    emergency_type = issue[0] or ''
                    emergency_display = issue[1] or 'Active emergency reported'
                    emergency_status = issue[2] or 'Open'

                # Dimensions string
                dims = '—'
                if cl and cw and ch:
                    dims = f"{float(cl):g} × {float(cw):g} × {float(ch):g} cm"

                delivery_list.append({
                    'id': delivery_id,
                    'sender': sender_name,
                    'sender_phone': sender_phone or '—',
                    'provider': provider_name,
                    'provider_vehicle': f"{vehicle_type} · {plate_number}" if vehicle_type else '—',
                    'status': status,
                    'delivery_type': pickup_type or '—',
                    'emergency': emergency_display,
                    'emergency_type': emergency_type,
                    'emergency_status': emergency_status,
                    'escrow_status': (escrow_status or 'On Hold').title(),
                    'escrow_id': escrow_id,
                    'escrow_amount': float(escrow_amount or 0),
                    'escrow_frozen': bool(emergency_frozen),
                    'escrow_tx_hash': bc_escrow_tx or '',
                    'chat_room_id': room_id,
                    'pickup_address': pickup_addr,
                    'dropoff_address': dropoff_addr,
                    'provider_lat': float(pu_lat) if pu_lat else '',   # note: swap to real provider GPS if you add it later
                    'provider_lng': float(pu_lng) if pu_lng else '',
                    'dropoff_lat': float(do_lat) if do_lat else '',
                    'dropoff_lng': float(do_lng) if do_lng else '',
                    'location_updated_at': '',
                    'status_history': status_history_str,
                    'requested_at': requested_at,
                    'accepted_at': accepted_at,
                    'eta': eta,
                    'completed_at': completed_at,
                    'pickup_verified': bool(pickup_verified),
                    'dropoff_verified': bool(dropoff_verified),
                    'cargo_description': cargo_desc or 'No description provided.',
                    'cargo_weight': float(weight) if weight else '',
                    'cargo_dimensions': dims,
                    'box_small': sb or 0,
                    'box_medium': mb or 0,
                    'box_large': lb or 0,
                    'is_fragile': bool(fragile),
                    'cargo_photo': cargo_pic or '',
                    'base_fee': float(base_amount or 0),
                    'service_fee': float(service_fee or 0),
                    'penalty_fee': float(penalty_fee or 0),
                    'total_amount': float(total_amount or 0),
                    'payment_method': payment_method or '—',
                    'payment_status': payment_status or '—',
                    'transaction_tx_hash': '',
                })

    except Exception as e:
        print(f"[deliveries] DB error: {e}")

    return render(request, 'pages/deliveries.html', {
        'deliveries': delivery_list,
    })


def generic_admin_page(request, title):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')
    return render(request, 'pages/generic_placeholder.html', {'page_title': title})

def escrow_payments(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab = request.GET.get('tab', 'active')

    escrow_list = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    ep.escrow_id,
                    ep.delivery_id,
                    ep.amount,
                    ep.escrow_status,
                    ep.emergency_frozen,
                    ep.created_at,
                    ep.bc_escrow_tx_hash,
                    ep.sender_id,
                    ep.provider_id,
                    CONCAT_WS(' ', s.first_name, s.last_name) AS sender_name,
                    CONCAT_WS(' ', p.first_name, p.last_name) AS provider_name
                FROM escrow_payments ep
                LEFT JOIN users s ON s.user_id = ep.sender_id
                LEFT JOIN users p ON p.user_id = ep.provider_id
                ORDER BY ep.created_at DESC
            """)
            rows = cursor.fetchall()

            # Map DB status values → display values used by the template
            status_map = {
                'completed':  'Released',
                'released':   'Released',
                'on hold':    'On Hold',
                'on_hold':    'On Hold',
                'on_hold ':   'On Hold',
                'frozen':     'Frozen',
                'refunded':   'Refunded',
                'cancelled':  'Cancelled',
                'canceled':   'Cancelled',
                'pending':    'On Hold',
            }

            for row in rows:
                (escrow_id, delivery_id, amount, raw_status, frozen,
                 created_at, tx_hash, sender_id, provider_id,
                 sender_name, provider_name) = row

                s_display = sender_name.strip() if sender_name and sender_name.strip() else f"USR-{sender_id}"
                p_display = provider_name.strip() if provider_name and provider_name.strip() else f"PRV-{provider_id}"

                raw_norm = (raw_status or '').strip()

                # ---- The key fix: 'Completed' → 'Released' ----
                display_status = status_map.get(raw_norm.lower())
                if not display_status:
                    display_status = raw_norm.title() if raw_norm else 'On Hold'

                # Frozen flag always overrides
                if frozen is True:
                    display_status = 'Frozen'

                print(f"[escrow] EID{escrow_id} raw='{raw_norm}' → display='{display_status}'")

                escrow_list.append({
                    'id': f"EID{escrow_id}",
                    'raw_id': escrow_id,
                    'delivery_id': delivery_id,
                    'sender_id': f"{s_display} (ID: {sender_id})",
                    'provider_id': f"{p_display} (ID: {provider_id})",
                    'amount': f"₱{float(amount or 0):,.2f}",
                    'escrow_status': display_status,
                    'raw_escrow_status': raw_norm,
                    'bc_escrow_tx_hash': tx_hash or '',
                    'emergency_frozen': bool(frozen),
                    'created_at': created_at.strftime('%Y-%m-%d %I:%M %p') if created_at else '—',
                })

    except Exception as e:
        print(f"[escrow_payments] Database query error: {e}")
        escrow_list = []

    # ---------------------------------------------------------------
    # Transaction History tab — real data
    # ---------------------------------------------------------------
    transactions_list = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    t.transaction_id,
                    t.escrow_id,
                    ep.delivery_id,
                    t.base_amount,
                    t.service_fee,
                    t.penalty_fee,
                    t.total_amount,
                    t.payment_method,
                    t.status,
                    t.processed_at
                FROM transactions t
                LEFT JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
                ORDER BY t.processed_at DESC NULLS LAST, t.transaction_id DESC
            """)
            for r in cursor.fetchall():
                (tid, escrow_id, delivery_id,
                 base_amount, service_fee, penalty_fee, total_amount,
                 payment_method, status, processed_at) = r

                transactions_list.append({
                    'id': f"TID{tid}",
                    'escrow_id': f"EID{escrow_id}" if escrow_id else '—',
                    'delivery_id': delivery_id or '—',
                    'base_amount': f"₱{float(base_amount or 0):,.2f}",
                    'service_fee': f"₱{float(service_fee or 0):,.2f}",
                    'penalty_fee': f"₱{float(penalty_fee or 0):,.2f}",
                    'total_amount': f"₱{float(total_amount or 0):,.2f}",
                    'method': payment_method or '—',
                    'status': (status or 'Pending').title(),
                    'processed_at': processed_at.strftime('%Y-%m-%d %I:%M %p') if processed_at else '—',
                })
    except Exception as e:
        print(f"[escrow_payments] transactions query error: {e}")
        transactions_list = []

    return render(request, 'pages/escrow_payments.html', {
        'current_tab': current_tab,
        'escrow_list': escrow_list,
        'transactions': transactions_list,
    })

def toggle_escrow_freeze(request):
    if not request.session.get('is_mock_logged_in'):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        escrow_id = data.get('escrow_id')
        
        # Remove 'EID' prefix if present to match the database bigint primary key
        if isinstance(escrow_id, str) and escrow_id.startswith('EID'):
            escrow_id = escrow_id.replace('EID', '')

        with connection.cursor() as cursor:
            # First, check current state
            cursor.execute("SELECT emergency_frozen FROM escrow_payments WHERE escrow_id = %s", [escrow_id])
            row = cursor.fetchone()
            
            if not row:
                return JsonResponse({'error': 'Escrow record not found'}, status=404)

            is_currently_frozen = row[0]
            new_frozen_state = not is_currently_frozen
            new_status = 'Frozen' if new_frozen_state else 'On hold'

            # Update database record
            cursor.execute("""
                UPDATE escrow_payments 
                SET emergency_frozen = %s,
                    escrow_status = %s
                WHERE escrow_id = %s
            """, [new_frozen_state, new_status, escrow_id])

        return JsonResponse({
            'status': 'success',
            'is_frozen': new_frozen_state,
            'escrow_status': new_status.title() # Returns 'Frozen' or 'On Hold'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def ratings_feedback(request):
    current_tab = request.GET.get('tab', 'overview')

    if request.method == 'POST':
        action = request.POST.get('action')
        review_id = request.POST.get('review_id')

        if action == 'remove' and review_id:
            messages.success(request, f"Review #REV-{review_id} has been successfully removed.")

        elif action == 'resolve' and review_id:
            messages.success(request, f"Dispute for Review #REV-{review_id} has been marked as resolved.")

        return redirect(f"{request.path}?tab={current_tab}")

    reviews_list = []
    disputes_list = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    review_id, 
                    rating, 
                    review_text, 
                    bc_rating_tx_hash, 
                    delivery_id, 
                    reviewer_id, 
                    reviewee_id, 
                    created_at 
                FROM ratings_reviews 
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()

            for row in rows:
                item = {
                    'review_id': row[0],
                    'rating': row[1],
                    'review_text': row[2],
                    'bc_rating_tx_hash': row[3],
                    'delivery_id': row[4],
                    'reviewer_id': row[5],
                    'reviewee_id': row[6],
                    'created_at': row[7].strftime('%Y-%m-%d') if row[7] else '—',
                    'status': 'Flagged' if row[1] <= 2 else 'Active'
                }

                reviews_list.append(item)
                if item['status'] == 'Flagged':
                    disputes_list.append(item)

    except Exception:
        reviews_list = [
            {
                'review_id': 101,
                'rating': 2,
                'review_text': 'Package left at wrong location and delayed by 2 hours.',
                'bc_rating_tx_hash': '0x8f2a9b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a',
                'delivery_id': 5001,
                'reviewer_id': 301,
                'reviewee_id': 402,
                'created_at': '2026-03-28',
                'status': 'Flagged'
            },
            {
                'review_id': 102,
                'rating': 1,
                'review_text': 'Very unprofessional handler. Item box was dented.',
                'bc_rating_tx_hash': '0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b',
                'delivery_id': 5002,
                'reviewer_id': 302,
                'reviewee_id': 403,
                'created_at': '2026-03-27',
                'status': 'Flagged'
            },
            {
                'review_id': 103,
                'rating': 5,
                'review_text': 'Very careful with my package. Arrived earlier than expected!',
                'bc_rating_tx_hash': '0x3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d',
                'delivery_id': 5003,
                'reviewer_id': 303,
                'reviewee_id': 403,
                'created_at': '2026-03-26',
                'status': 'Active'
            },
        ]

        disputes_list = [r for r in reviews_list if r['status'] == 'Flagged']

    context = {
        'current_tab': current_tab,
        'reviews_list': reviews_list,
        'disputes_list': disputes_list,
    }

    return render(request, 'pages/ratings_feedback.html', context)


def reports(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab     = request.GET.get('tab', 'overview')
    selected_period = request.GET.get('period', 'this_month')

    delivery_type  = request.GET.get('delivery_type', '')
    status_filter  = request.GET.get('status', '')
    payment_method = request.GET.get('payment_method', '')
    role_filter    = request.GET.get('role', '')
    proof_type     = request.GET.get('proof_type', '')

    # --- period → date range --------------------------------------------------
    period_days = {
        'this_month':     30,
        'last_month':     60,
        'last_3_months':  90,
        'this_year':      365,
    }
    days = period_days.get(selected_period, 30)

    ctx = {
        'current_tab': current_tab,
        'selected_period': selected_period,
        'delivery_type': delivery_type,
        'status_filter': status_filter,
        'payment_method': payment_method,
        'role_filter': role_filter,
        'proof_type': proof_type,

        # defaults (safely replaced below)
        'chart_labels': json.dumps([]),
        'overview_delivery_values': json.dumps([]),
        'overview_revenue_values': json.dumps([]),
        'net_revenue_values': json.dumps([]),
        'week_labels': json.dumps([]),
        'week_completed': json.dumps([]),
        'week_cancelled': json.dumps([]),
        'week_pending': json.dumps([]),
        'delivery_type_labels': json.dumps(['Curb-side', 'Door-to-Door']),
        'delivery_type_values': json.dumps([0, 0]),
        'payment_method_labels': json.dumps(['GCash', 'Card', 'Bank Transfer']),
        'payment_method_values': json.dumps([0, 0, 0]),
        'signup_senders': json.dumps([]),
        'signup_providers': json.dumps([]),
        'weekly_rows': [],
        'top_providers': [],
        'recent_transactions': [],
        'blockchain_records': [],

        # overview defaults
        'ov_completed': '0', 'ov_net_revenue': '₱0',
        'ov_fulfillment_rate': '0.0%', 'ov_cancellation_rate': '0.0%',
        'ov_dispute_rate': '0.0%', 'ov_active_users': '0', 'ov_new_users': '0',

        # deliveries defaults
        'del_total': '0', 'del_completion': '0.0%', 'del_cancel': '0.0%',
        'del_avg_duration': '0m', 'del_exception': '0.0%',

        # financial defaults
        'fin_gmv': '₱0', 'fin_net': '₱0', 'fin_take_rate': '0.0%',
        'fin_escrow_held': '₱0', 'fin_refunded': '₱0',

        # users defaults
        'usr_new_signups': '0', 'usr_active_senders': '0', 'usr_active_providers': '0',
        'usr_repeat_rate': '0.0%', 'usr_pending_verifications': '0',

        # blockchain defaults
        'bc_total_proofs': '0', 'bc_pickup_rate': '0.0%',
        'bc_dropoff_rate': '0.0%', 'bc_escrow_anchored': '0',
    }

    try:
        with connection.cursor() as cursor:

            # ==========================================================
            # Monthly labels + series (shared across tabs), last 6 months
            # ==========================================================
            cursor.execute("""
                WITH months AS (
                    SELECT DATE_TRUNC('month', CURRENT_DATE) - (n || ' month')::interval AS m
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT
                    TO_CHAR(m, 'Mon') AS label,
                    m
                FROM months
                ORDER BY m
            """)
            month_rows = cursor.fetchall()
            month_labels = [r[0] for r in month_rows]
            month_starts = [r[1] for r in month_rows]

            ctx['chart_labels'] = json.dumps(month_labels)

            # --- deliveries per month (completed) ----------------------
            cursor.execute("""
                SELECT DATE_TRUNC('month', d.accepted_at) AS m,
                       COUNT(*) FILTER (WHERE dsh_latest.status = 'Completed') AS completed_cnt
                FROM deliveries d
                LEFT JOIN LATERAL (
                    SELECT status FROM delivery_status_history
                    WHERE delivery_id = d.delivery_id
                    ORDER BY updated_at DESC LIMIT 1
                ) dsh_latest ON true
                WHERE d.accepted_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                GROUP BY m
                ORDER BY m
            """)
            del_by_month = {r[0].replace(day=1): r[1] for r in cursor.fetchall()}
            ctx['overview_delivery_values'] = json.dumps(
                [int(del_by_month.get(m.replace(day=1), 0)) for m in month_starts]
            )

            # --- revenue per month (transactions total) ----------------
            cursor.execute("""
                SELECT DATE_TRUNC('month', processed_at) AS m,
                       COALESCE(SUM(total_amount), 0) AS total_rev,
                       COALESCE(SUM(service_fee + penalty_fee), 0) AS net_rev
                FROM transactions
                WHERE status IN ('Completed', 'Released')
                  AND processed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                GROUP BY m
                ORDER BY m
            """)
            rev_by_month = {r[0].replace(day=1): (float(r[1]), float(r[2])) for r in cursor.fetchall()}
            ctx['overview_revenue_values'] = json.dumps(
                [float(rev_by_month.get(m.replace(day=1), (0, 0))[0]) for m in month_starts]
            )
            ctx['net_revenue_values'] = json.dumps(
                [float(rev_by_month.get(m.replace(day=1), (0, 0))[1]) for m in month_starts]
            )

            # ==========================================================
            # OVERVIEW
            # ==========================================================
            cursor.execute("""
                WITH latest_status AS (
                    SELECT DISTINCT ON (delivery_id) delivery_id, status
                    FROM delivery_status_history
                    ORDER BY delivery_id, updated_at DESC
                )
                SELECT
                    COUNT(*) FILTER (WHERE ls.status = 'Completed') AS completed_cnt,
                    COUNT(*) FILTER (WHERE ls.status = 'Cancelled') AS cancelled_cnt,
                    COUNT(*) AS total_cnt
                FROM deliveries d
                LEFT JOIN latest_status ls ON ls.delivery_id = d.delivery_id
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            if row:
                completed_cnt, cancelled_cnt, total_cnt = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
                ctx['ov_completed'] = str(completed_cnt)
                ctx['ov_fulfillment_rate'] = f"{(completed_cnt / total_cnt * 100):.1f}%" if total_cnt else '0.0%'
                ctx['ov_cancellation_rate'] = f"{(cancelled_cnt / total_cnt * 100):.1f}%" if total_cnt else '0.0%'

            cursor.execute("""
                SELECT COALESCE(SUM(service_fee + penalty_fee), 0)
                FROM transactions
                WHERE status IN ('Completed', 'Released')
                  AND processed_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            rev = float(cursor.fetchone()[0] or 0)
            ctx['ov_net_revenue'] = f"₱{rev:,.0f}"

            cursor.execute("""
                SELECT COUNT(*) FROM delivery_issues
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            issues_cnt = int(cursor.fetchone()[0] or 0)
            ctx['ov_dispute_rate'] = f"{(issues_cnt / completed_cnt * 100):.1f}%" if completed_cnt else '0.0%'

            cursor.execute("""
                SELECT
                    COUNT(DISTINCT u.user_id) AS active_users,
                    COUNT(*) FILTER (WHERE u.created_at >= CURRENT_DATE - (%s || ' days')::interval) AS new_users
                FROM users u
                WHERE u.is_active = TRUE
            """, [days])
            row = cursor.fetchone()
            if row:
                ctx['ov_active_users'] = str(int(row[0] or 0))
                ctx['ov_new_users'] = str(int(row[1] or 0))

            # ==========================================================
            # DELIVERIES TAB
            # ==========================================================
            del_where = ["d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval"]
            del_params = [days]
            if status_filter:
                # map to canonical statuses in delivery_status_history
                mapping = {
                    'completed': 'Completed',
                    'cancelled': 'Cancelled',
                    'in_transit': 'In Transit',
                    'pending': 'Pending',
                }
                if status_filter in mapping:
                    del_where.append("ls.status = %s")
                    del_params.append(mapping[status_filter])

            cursor.execute(f"""
                WITH latest_status AS (
                    SELECT DISTINCT ON (delivery_id) delivery_id, status
                    FROM delivery_status_history
                    ORDER BY delivery_id, updated_at DESC
                ),
                latest_type AS (
                    SELECT d.delivery_id, dr.pickup_type
                    FROM deliveries d
                    JOIN delivery_requests dr ON dr.request_id = d.request_id
                )
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE ls.status = 'Completed') AS completed,
                    COUNT(*) FILTER (WHERE ls.status = 'Cancelled') AS cancelled,
                    AVG(EXTRACT(EPOCH FROM (d.completed_at - d.accepted_at)) / 60)
                        FILTER (WHERE d.completed_at IS NOT NULL) AS avg_minutes
                FROM deliveries d
                LEFT JOIN latest_status ls ON ls.delivery_id = d.delivery_id
                LEFT JOIN latest_type lt   ON lt.delivery_id = d.delivery_id
                WHERE {' AND '.join(del_where)}
            """, del_params)
            row = cursor.fetchone()
            if row:
                total, comp, canc, avg_min = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), row[3]
                ctx['del_total'] = str(total)
                ctx['del_completion'] = f"{(comp / total * 100):.1f}%" if total else '0.0%'
                ctx['del_cancel'] = f"{(canc / total * 100):.1f}%" if total else '0.0%'
                ctx['del_avg_duration'] = f"{int(avg_min)}m" if avg_min else '—'

                cursor.execute("""
                    SELECT COUNT(*) FROM delivery_issues
                    WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
                """, [days])
                exc = int(cursor.fetchone()[0] or 0)
                ctx['del_exception'] = f"{(exc / comp * 100):.1f}%" if comp else '0.0%'

            # Weekly breakdown (last 6 weeks)
            cursor.execute("""
                WITH weeks AS (
                    SELECT DATE_TRUNC('week', CURRENT_DATE) - (n || ' week')::interval AS w
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT
                    TO_CHAR(w, '"W"IW') AS label,
                    w
                FROM weeks
                ORDER BY w
            """)
            week_starts = cursor.fetchall()
            week_labels = [r[0] for r in week_starts]
            ctx['week_labels'] = json.dumps(week_labels)

            cursor.execute("""
                WITH latest_status AS (
                    SELECT DISTINCT ON (delivery_id) delivery_id, status
                    FROM delivery_status_history
                    ORDER BY delivery_id, updated_at DESC
                )
                SELECT
                    DATE_TRUNC('week', d.accepted_at) AS w,
                    COUNT(*) FILTER (WHERE ls.status = 'Completed') AS c,
                    COUNT(*) FILTER (WHERE ls.status = 'Cancelled') AS x,
                    COUNT(*) FILTER (WHERE ls.status IN ('Pending', 'Accepted', 'In Transit')) AS p,
                    COUNT(*) AS total,
                    AVG(EXTRACT(EPOCH FROM (d.completed_at - d.accepted_at)) / 60)
                        FILTER (WHERE d.completed_at IS NOT NULL) AS avg_min
                FROM deliveries d
                LEFT JOIN latest_status ls ON ls.delivery_id = d.delivery_id
                WHERE d.accepted_at >= DATE_TRUNC('week', CURRENT_DATE) - INTERVAL '5 weeks'
                GROUP BY w
                ORDER BY w
            """)
            wk_map = {}
            for r in cursor.fetchall():
                wk_map[r[0].replace(hour=0, minute=0, second=0, microsecond=0)] = {
                    'c': int(r[1] or 0), 'x': int(r[2] or 0), 'p': int(r[3] or 0),
                    'total': int(r[4] or 0), 'avg': int(r[5]) if r[5] else 0,
                }

            wc, wx, wp, weekly_rows = [], [], [], []
            for label, w_start in week_starts:
                wkey = w_start.replace(hour=0, minute=0, second=0, microsecond=0)
                data = wk_map.get(wkey, {'c':0,'x':0,'p':0,'total':0,'avg':0})
                wc.append(data['c']); wx.append(data['x']); wp.append(data['p'])
                weekly_rows.append({
                    'label': label,
                    'requests': data['total'],
                    'completed': data['c'],
                    'cancelled': data['x'],
                    'duration': f"{data['avg']} min" if data['avg'] else '—',
                })
            ctx['week_completed'] = json.dumps(wc)
            ctx['week_cancelled'] = json.dumps(wx)
            ctx['week_pending']   = json.dumps(wp)
            ctx['weekly_rows']    = weekly_rows

            # Delivery type split
            cursor.execute("""
                WITH latest_status AS (
                    SELECT DISTINCT ON (delivery_id) delivery_id, status
                    FROM delivery_status_history
                    ORDER BY delivery_id, updated_at DESC
                )
                SELECT dr.pickup_type, COUNT(*)
                FROM deliveries d
                JOIN delivery_requests dr ON dr.request_id = d.request_id
                LEFT JOIN latest_status ls ON ls.delivery_id = d.delivery_id
                WHERE ls.status = 'Completed'
                  AND d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY dr.pickup_type
            """, [days])
            type_counts = {'curbside': 0, 'door': 0}
            for ptype, cnt in cursor.fetchall():
                key = (ptype or '').lower().replace('-','').replace('_','')
                if 'door' in key: type_counts['door'] = int(cnt)
                else: type_counts['curbside'] = int(cnt)
            ctx['delivery_type_values'] = json.dumps([type_counts['curbside'], type_counts['door']])

            # ==========================================================
            # FINANCIAL TAB
            # ==========================================================
            cursor.execute("""
                SELECT
                    COALESCE(SUM(total_amount), 0) AS gmv,
                    COALESCE(SUM(service_fee + penalty_fee), 0) AS net
                FROM transactions
                WHERE processed_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            gmv, net = float(row[0] or 0), float(row[1] or 0)
            ctx['fin_gmv'] = f"₱{gmv:,.0f}"
            ctx['fin_net'] = f"₱{net:,.0f}"
            ctx['fin_take_rate'] = f"{(net / gmv * 100):.1f}%" if gmv else '0.0%'

            cursor.execute("""
                SELECT
                    COALESCE(SUM(amount) FILTER (WHERE escrow_status ILIKE 'on hold'), 0) AS held,
                    COALESCE(SUM(amount) FILTER (WHERE escrow_status ILIKE 'refunded'), 0) AS refunded
                FROM escrow_payments
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            ctx['fin_escrow_held'] = f"₱{float(row[0] or 0):,.0f}"
            ctx['fin_refunded']    = f"₱{float(row[1] or 0):,.0f}"

            # Payment method breakdown
            cursor.execute("""
                SELECT payment_method, COALESCE(SUM(total_amount), 0)
                FROM transactions
                WHERE processed_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY payment_method
                ORDER BY 2 DESC
            """, [days])
            pm_rows = cursor.fetchall()
            pm_labels = [r[0] or 'Other' for r in pm_rows] or ['No data']
            pm_values = [float(r[1] or 0) for r in pm_rows] or [0]
            ctx['payment_method_labels'] = json.dumps(pm_labels)
            ctx['payment_method_values'] = json.dumps(pm_values)

            # Recent transactions
            cursor.execute("""
                SELECT
                    t.transaction_id,
                    ep.delivery_id,
                    t.total_amount,
                    t.payment_method,
                    t.status
                FROM transactions t
                LEFT JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
                ORDER BY t.processed_at DESC NULLS LAST, t.transaction_id DESC
                LIMIT 5
            """)
            recent = []
            for r in cursor.fetchall():
                recent.append({
                    'id': f"TID{r[0]}",
                    'delivery_id': r[1] or '—',
                    'amount': f"₱{float(r[2] or 0):,.2f}",
                    'method': (r[3] or '—'),
                    'status': (r[4] or 'Pending'),
                })
            ctx['recent_transactions'] = recent

            # ==========================================================
            # USERS TAB
            # ==========================================================
            cursor.execute("""
                SELECT COUNT(*) FROM users
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['usr_new_signups'] = str(int(cursor.fetchone()[0] or 0))

            cursor.execute("""
                SELECT
                    COUNT(DISTINCT u.user_id) FILTER (WHERE r.role_name ILIKE 'sender')   AS senders,
                    COUNT(DISTINCT u.user_id) FILTER (WHERE r.role_name ILIKE 'provider') AS providers
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.user_id
                JOIN roles r       ON r.role_id  = ur.role_id
                WHERE u.is_active = TRUE
            """)
            row = cursor.fetchone()
            ctx['usr_active_senders']   = str(int(row[0] or 0))
            ctx['usr_active_providers'] = str(int(row[1] or 0))

            cursor.execute("""
                SELECT
                    COUNT(DISTINCT dr.sender_id) AS repeat_senders,
                    (SELECT COUNT(DISTINCT sender_id) FROM delivery_requests) AS total_senders
                FROM delivery_requests dr
                GROUP BY dr.sender_id
            """)
            row = cursor.fetchone()
            if row and row[1]:
                ctx['usr_repeat_rate'] = f"{(row[0] / row[1] * 100):.1f}%"

            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM provider_verifications WHERE verification_status = 'Pending') +
                    (SELECT COUNT(*) FROM vehicles WHERE verification_status = 'Pending')
            """)
            ctx['usr_pending_verifications'] = str(int(cursor.fetchone()[0] or 0))

            # Signups per month
            cursor.execute("""
                WITH months AS (
                    SELECT DATE_TRUNC('month', CURRENT_DATE) - (n || ' month')::interval AS m
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT
                    m,
                    COALESCE(SUM(CASE WHEN r.role_name ILIKE 'sender'   THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN r.role_name ILIKE 'provider' THEN 1 ELSE 0 END), 0)
                FROM months
                LEFT JOIN users u
                    ON DATE_TRUNC('month', u.created_at) = m
                LEFT JOIN user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN roles r       ON r.role_id  = ur.role_id
                GROUP BY m
                ORDER BY m
            """)
            ss, sp = [], []
            for _, s, p in cursor.fetchall():
                ss.append(int(s)); sp.append(int(p))
            ctx['signup_senders']   = json.dumps(ss)
            ctx['signup_providers'] = json.dumps(sp)

            # Top providers
            cursor.execute("""
                SELECT
                    u.user_id,
                    COALESCE(NULLIF(CONCAT_WS(' ', u.first_name, u.last_name), ''), 'Provider #' || u.user_id) AS name,
                    COUNT(*) FILTER (WHERE ls.status = 'Completed') AS completed,
                    COALESCE(ROUND(AVG(rr.rating)::numeric, 1), 0) AS rating,
                    COALESCE(SUM(ep.amount) FILTER (WHERE ep.escrow_status = 'Released'), 0) AS earnings
                FROM users u
                JOIN deliveries d ON d.provider_id = u.user_id
                LEFT JOIN delivery_status_history ls ON ls.delivery_id = d.delivery_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN ratings_reviews rr ON rr.reviewee_id = u.user_id
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY u.user_id, u.first_name, u.last_name
                ORDER BY earnings DESC
                LIMIT 3
            """, [days])
            top = []
            for r in cursor.fetchall():
                top.append({
                    'name': r[1],
                    'completed': int(r[2] or 0),
                    'rating': float(r[3] or 0),
                    'earnings': f"₱{float(r[4] or 0):,.0f}",
                })
            ctx['top_providers'] = top

            # ==========================================================
            # BLOCKCHAIN AUDIT
            # ==========================================================
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM qr_verifications WHERE pickup_verified = TRUE) +
                    (SELECT COUNT(*) FROM qr_verifications WHERE dropoff_verified = TRUE) +
                    (SELECT COUNT(*) FROM escrow_payments WHERE bc_escrow_tx_hash IS NOT NULL)
            """)
            ctx['bc_total_proofs'] = str(int(cursor.fetchone()[0] or 0))

            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE pickup_verified = TRUE)::float / NULLIF(COUNT(*), 0) * 100,
                    COUNT(*) FILTER (WHERE dropoff_verified = TRUE)::float / NULLIF(COUNT(*), 0) * 100
                FROM qr_verifications
            """)
            row = cursor.fetchone()
            if row:
                ctx['bc_pickup_rate'] = f"{float(row[0] or 0):.1f}%"
                ctx['bc_dropoff_rate'] = f"{float(row[1] or 0):.1f}%"

            cursor.execute("""
                SELECT COUNT(*) FROM escrow_payments
                WHERE bc_escrow_tx_hash IS NOT NULL
                  AND created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['bc_escrow_anchored'] = str(int(cursor.fetchone()[0] or 0))

            # Recent on-chain records
            records = []
            cursor.execute("""
                SELECT delivery_id, bc_escrow_tx_hash, created_at
                FROM escrow_payments
                WHERE bc_escrow_tx_hash IS NOT NULL
                ORDER BY created_at DESC NULLS LAST
                LIMIT 5
            """)
            for r in cursor.fetchall():
                records.append({
                    'delivery_id': r[0],
                    'proof_type': 'Escrow',
                    'tx_hash': r[1] or '',
                    'recorded_at': r[2].strftime('%b %d, %Y') if r[2] else '—',
                })
            ctx['blockchain_records'] = records

    except Exception as e:
        print(f"[reports] DB error: {e}")

    return render(request, 'pages/reports.html', ctx)


def settings_page(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    settings_data = {
        'door_to_door': '20.00',
        'platform_commission': '8.5',
        'base_fare': '49.00',
        'per_km_rate': '14.50',
    }

    try:
        with connection.cursor() as cursor:

            # -----------------------------------------------------------
            # Save
            # -----------------------------------------------------------
            if request.method == 'POST':
                new_door_to_door       = request.POST.get('door_to_door', settings_data['door_to_door'])
                new_platform_commission = request.POST.get('platform_commission', settings_data['platform_commission'])
                new_base_fare          = request.POST.get('base_fare', settings_data['base_fare'])
                new_per_km_rate        = request.POST.get('per_km_rate', settings_data['per_km_rate'])

                # Look for the most recent rate row (single active row pattern).
                cursor.execute("""
                    SELECT rate_id
                    FROM delivery_rates
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()

                if row:
                    # Update the existing active row
                    cursor.execute("""
                        UPDATE delivery_rates
                        SET small_box_fee  = %s,
                            base_rate      = %s,
                            per_km_rate    = %s,
                            updated_at     = NOW()
                        WHERE rate_id = %s
                    """, [
                        float(new_door_to_door or 0),
                        float(new_base_fare or 0),
                        float(new_per_km_rate or 0),
                        row[0],
                    ])
                else:
                    # First-time insert (no rows yet)
                    cursor.execute("""
                        INSERT INTO delivery_rates
                            (delivery_type, small_box_fee, medium_box_fee, large_box_fee, base_rate, per_km_rate, updated_at)
                        VALUES
                            ('Standard', %s, 0, 0, %s, %s, NOW())
                    """, [
                        float(new_door_to_door or 0),
                        float(new_base_fare or 0),
                        float(new_per_km_rate or 0),
                    ])

                # platform_commission has no dedicated column in the schema.
                # Best fit: keep it in session so the operator can see it persisted
                # in-session until you add a `platform_commission` column to delivery_rates.
                request.session['platform_commission'] = new_platform_commission

                messages.success(request, 'Settings updated successfully!')

                settings_data = {
                    'door_to_door': new_door_to_door,
                    'platform_commission': new_platform_commission,
                    'base_fare': new_base_fare,
                    'per_km_rate': new_per_km_rate,
                }
                return render(request, 'pages/settings.html', {'settings': settings_data})

            # -----------------------------------------------------------
            # Read
            # -----------------------------------------------------------
            cursor.execute("""
                SELECT small_box_fee, base_rate, per_km_rate, updated_at
                FROM delivery_rates
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()

            if row:
                settings_data['door_to_door'] = f"{float(row[0] or 0):.2f}"
                settings_data['base_fare']    = f"{float(row[1] or 0):.2f}"
                settings_data['per_km_rate']  = f"{float(row[2] or 0):.2f}"

            # Platform commission isn't in the schema, so fall back to
            # whatever was set in this session, or the default.
            settings_data['platform_commission'] = request.session.get(
                'platform_commission', settings_data['platform_commission']
            )

    except Exception as e:
        print(f"[settings_page] DB error: {e}")

    return render(request, 'pages/settings.html', {
        'settings': settings_data,
    })


def custom_logout(request):
    if 'is_mock_logged_in' in request.session:
        del request.session['is_mock_logged_in']
    return redirect('login')


# ==========================================
# RESTORED MESSAGES VIEWS
# ==========================================
def messages_view(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab = request.GET.get('tab', 'all')
    selected_room_id = request.GET.get('room_id') or (MOCK_CONVERSATIONS[0]['room_id'] if MOCK_CONVERSATIONS else '')

    conversations = MOCK_CONVERSATIONS
    if current_tab == 'active':
        conversations = [c for c in MOCK_CONVERSATIONS if '1002' in c['delivery_id']]

    active_conversation = next((c for c in MOCK_CONVERSATIONS if c['room_id'] == selected_room_id), MOCK_CONVERSATIONS[0] if MOCK_CONVERSATIONS else None)

    context = {
        'conversations': conversations,
        'current_tab': current_tab,
        'active_room_id': selected_room_id,
        'active_conversation': active_conversation,
    }

    try:
        return render(request, 'pages/messages.html', context)
    except TemplateDoesNotExist:
        return render(request, 'messages.html', context)


def message_thread_api(request, room_id):
    if not request.session.get('is_mock_logged_in'):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    conv = next((c for c in MOCK_CONVERSATIONS if c['room_id'] == str(room_id) or c['room_id'] == f"room_{room_id}"), None)
    if not conv:
        return JsonResponse({'messages': [], 'delivery_id': 0})

    return JsonResponse({
        'room_id': conv['room_id'],
        'delivery_id': conv['delivery_id'],
        'sender': conv['sender'],
        'provider': conv['provider'],
        'messages': conv['messages']
    })


def send_message_api(request, room_id):
    if not request.session.get('is_mock_logged_in'):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message_text = data.get('message', '').strip()
            if not message_text:
                return JsonResponse({'error': 'Empty message'}, status=400)

            conv = next((c for c in MOCK_CONVERSATIONS if c['room_id'] == str(room_id) or c['room_id'] == f"room_{room_id}"), None)
            if conv:
                new_msg = {
                    'sender_id': 0,
                    'sender_name': 'Admin',
                    'sender_role': 'admin',
                    'message': message_text,
                    'sent_at': 'Just now'
                }
                conv['messages'].append(new_msg)
                conv['last_message'] = message_text
                conv['updated_at'] = 'Just now'
                return JsonResponse({'status': 'success', 'message': new_msg})

            return JsonResponse({'error': 'Room not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid method'}, status=405)


def admin_support_view(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    try:
        return render(request, 'pages/admin_support_inbox.html')
    except TemplateDoesNotExist:
        return render(request, 'admin_support_inbox.html')