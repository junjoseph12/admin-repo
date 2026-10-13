from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse
from .models import ProviderVerification
from django.contrib import messages
from django.db import connection
from django.template.exceptions import TemplateDoesNotExist
from functools import wraps
import os
import json


# ==========================================
# ADMIN-ONLY GUARD DECORATOR
# ==========================================
def admin_required(view_func):
    """
    Simple session-based guard. Only requires that the admin has logged in
    with the correct credentials during this session.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get('is_mock_logged_in'):
            return redirect('login')
        return view_func(request, *args, **kwargs)

    return _wrapped


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


# ==========================================
# ADMIN LOGIN (simple mock: admin / admin)
# ==========================================
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


# ==========================================
# DASHBOARD
# ==========================================
@admin_required
def dashboard(request):
    stats = {
        'total_users': 0,
        'total_deliveries': 0,
        'total_revenue': 0.0,
        'pending_deliveries': 0,
    }
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


# ==========================================
# USERS
# ==========================================
@admin_required
def users_page(request):
    current_tab = request.GET.get('tab', 'all')
    providers = []
    senders = []

    try:
        with connection.cursor() as cursor:
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
                        v.verification_status AS vehicle_verif_status,
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

                    -- One vehicle per provider (avoids duplicate rows)
                    LEFT JOIN LATERAL (
                        SELECT vehicle_type, plate_number, verification_status
                        FROM vehicles
                        WHERE provider_id = u.user_id
                        ORDER BY vehicle_id ASC
                        LIMIT 1
                    ) v ON true

                    -- One verification record per provider (avoids duplicate rows)
                    LEFT JOIN LATERAL (
                        SELECT verification_status
                        FROM provider_verifications
                        WHERE provider_id = u.user_id
                        ORDER BY submitted_at DESC NULLS LAST
                        LIMIT 1
                    ) pv ON true

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
                      AND ur.role_id = (SELECT role_id FROM roles WHERE role_name ILIKE 'provider' LIMIT 1)
                    ORDER BY u.created_at DESC
                """)

                for row in cursor.fetchall():
                    (user_id, first_name, middle_name, last_name, email, phone,
                     is_verified, is_active, created_at,
                     p_street, p_barangay, p_city, p_province,
                     vehicle_type, plate_number, vehicle_verif_status,
                     provider_verif_status,
                     wallet_balance,
                     total_deliveries, completed, cancelled, active_deliveries,
                     total_earnings, avg_rating, dispute_count) = row

                    full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{user_id}"
                    addr_primary = ", ".join(filter(None, [p_street, p_barangay, p_city, p_province])) or '—'
                    addr_other = '—'
                    vehicle_display = f"{vehicle_type} · {plate_number}" if vehicle_type and plate_number else '—'

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
                      AND ur.role_id = (SELECT role_id FROM roles WHERE role_name ILIKE 'sender' LIMIT 1)
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
        print(f"[users_page] DB error: {e}")

    return render(request, 'pages/users.html', {
        'users': providers,
        'senders': senders,
        'current_tab': current_tab,
    })

# ==========================================
# PROVIDER VERIFICATION
# ==========================================
@admin_required
def provider_verification(request):
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

            for row in cursor.fetchall():
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


@admin_required
def approve_provider(request, user_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT verification_id FROM provider_verifications
                    WHERE provider_id = %s
                    ORDER BY submitted_at DESC LIMIT 1
                """, [user_id])
                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE provider_verifications
                        SET verification_status = 'Approved', verified_at = NOW()
                        WHERE provider_id = %s
                    """, [user_id])
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, verified_at, provider_id)
                        VALUES (%s, NOW()::date, 'N/A', 'Approved', NOW(), %s)
                    """, [placeholder_license, user_id])

                cursor.execute("UPDATE users SET is_verified = TRUE WHERE user_id = %s", [user_id])

            messages.success(request, f'Provider (US{user_id}) approved successfully.')
        except Exception as e:
            print(f"[approve_provider] DB error: {e}")
            messages.error(request, f'Failed to approve provider: {e}')

    return redirect('provider_verification')


@admin_required
def reject_provider(request, user_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT verification_id FROM provider_verifications
                    WHERE provider_id = %s
                    ORDER BY submitted_at DESC LIMIT 1
                """, [user_id])
                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE provider_verifications
                        SET verification_status = 'Rejected'
                        WHERE provider_id = %s
                    """, [user_id])
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, provider_id)
                        VALUES (%s, NOW()::date, 'N/A', 'Rejected', %s)
                    """, [placeholder_license, user_id])

                cursor.execute("UPDATE users SET is_verified = FALSE WHERE user_id = %s", [user_id])

            messages.success(request, f'Provider (US{user_id}) rejected.')
        except Exception as e:
            print(f"[reject_provider] DB error: {e}")
            messages.error(request, f'Failed to reject provider: {e}')

    return redirect('provider_verification')


# ==========================================
# VEHICLE VERIFICATION
# ==========================================
@admin_required
def vehicle_verification(request):
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
                    v.vehicle_id, v.vehicle_type, v.plate_number,
                    v.max_volume_liters, v.max_weight_kg,
                    v.cargo_length_cm, v.cargo_width_cm, v.cargo_height_cm,
                    v.vehicle_doc,
                    COALESCE(v.verification_status, 'Pending') AS verification_status,
                    v.provider_id,
                    u.first_name, u.middle_name, u.last_name,
                    u.email, u.phone_number,
                    pv.verification_status AS provider_verif_status
                FROM vehicles v
                JOIN users u ON u.user_id = v.provider_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                WHERE COALESCE(v.verification_status, 'Pending') = ANY(%s)
                ORDER BY v.vehicle_id DESC
            """, [status_filter])

            for row in cursor.fetchall():
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


@admin_required
def approve_vehicle(request, vehicle_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE vehicles SET verification_status = 'Verified' WHERE vehicle_id = %s", [vehicle_id])
            messages.success(request, f'Vehicle #{vehicle_id} approved successfully.')
        except Exception as e:
            print(f"[approve_vehicle] DB error: {e}")
            messages.error(request, f'Failed to approve vehicle: {e}')
    return redirect('vehicle_verification')


@admin_required
def reject_vehicle(request, vehicle_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE vehicles SET verification_status = 'Rejected' WHERE vehicle_id = %s", [vehicle_id])
            messages.success(request, f'Vehicle #{vehicle_id} rejected.')
        except Exception as e:
            print(f"[reject_vehicle] DB error: {e}")
            messages.error(request, f'Failed to reject vehicle: {e}')
    return redirect('vehicle_verification')


# ==========================================
# DELIVERIES
# ==========================================
@admin_required
def deliveries(request):
    delivery_list = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    d.delivery_id, d.accepted_at, d.estimated_eta, d.completed_at,
                    s.user_id, s.first_name, s.middle_name, s.last_name, s.phone_number,
                    p.user_id, p.first_name, p.middle_name, p.last_name,
                    v.vehicle_type, v.plate_number,
                    pl.street_address, pl.barangay, pl.city, pl.province, pl.latitude, pl.longitude,
                    dl.street_address, dl.barangay, dl.city, dl.province, dl.latitude, dl.longitude,
                    dr.pickup_type, dr.delivery_status, dr.emergency_flag, dr.total_distance,
                    dr.estimated_cost, dr.created_at, dr.receiver_phone,
                    cp.description, cp.cargo_pic, cp.total_weight_kg,
                    cp.cargo_length_cm, cp.cargo_width_cm, cp.cargo_height_cm,
                    cp.small_box_qty, cp.medium_box_qty, cp.large_box_qty, cp.is_fragile,
                    dsh.status, dsh.updated_at,
                    ep.escrow_id, ep.amount, ep.escrow_status, ep.emergency_frozen, ep.bc_escrow_tx_hash,
                    t.base_amount, t.service_fee, t.penalty_fee, t.total_amount,
                    t.payment_method, t.status, t.processed_at,
                    cr.room_id,
                    qr.pickup_verified, qr.dropoff_verified
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
                    SELECT status, updated_at FROM delivery_status_history
                    WHERE delivery_id = d.delivery_id
                    ORDER BY updated_at DESC LIMIT 1
                ) dsh ON true
                ORDER BY d.accepted_at DESC
            """)

            for row in cursor.fetchall():
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
                status = latest_status or delivery_status or 'Pending'

                cursor.execute("""
                    SELECT status, updated_at FROM delivery_status_history
                    WHERE delivery_id = %s ORDER BY updated_at ASC
                """, [delivery_id])
                status_history_str = ";".join(
                    f"{st}|{ts.strftime('%b %d, %Y — %I:%M %p') if ts else '—'}"
                    for st, ts in cursor.fetchall()
                )

                cursor.execute("""
                    SELECT issue_type, description, status FROM delivery_issues
                    WHERE delivery_id = %s ORDER BY created_at DESC LIMIT 1
                """, [delivery_id])
                issue = cursor.fetchone()

                emergency_display = 'None'
                emergency_type = ''
                emergency_status = ''
                if emergency_flag and issue:
                    emergency_type = issue[0] or ''
                    emergency_display = issue[1] or 'Active emergency reported'
                    emergency_status = issue[2] or 'Open'

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
                    'provider_lat': float(pu_lat) if pu_lat else '',
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

    return render(request, 'pages/deliveries.html', {'deliveries': delivery_list})


# ==========================================
# ESCROW PAYMENTS
# ==========================================
@admin_required
def escrow_payments(request):
    current_tab = request.GET.get('tab', 'active')
    escrow_list = []
    transactions_list = []

    status_map = {
        'completed':  'Released', 'released':   'Released',
        'on hold':    'On Hold',  'on_hold':    'On Hold',
        'frozen':     'Frozen',   'refunded':   'Refunded',
        'cancelled':  'Cancelled','canceled':   'Cancelled',
        'pending':    'On Hold',
    }

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    ep.escrow_id, ep.delivery_id, ep.amount, ep.escrow_status,
                    ep.emergency_frozen, ep.created_at, ep.bc_escrow_tx_hash,
                    ep.sender_id, ep.provider_id,
                    CONCAT_WS(' ', s.first_name, s.last_name) AS sender_name,
                    CONCAT_WS(' ', p.first_name, p.last_name) AS provider_name
                FROM escrow_payments ep
                LEFT JOIN users s ON s.user_id = ep.sender_id
                LEFT JOIN users p ON p.user_id = ep.provider_id
                WHERE LOWER(ep.escrow_status) NOT IN ('released', 'completed', 'refunded', 'cancelled')
                   OR ep.escrow_status IS NULL
                ORDER BY ep.created_at DESC
            """)
            for row in cursor.fetchall():
                (escrow_id, delivery_id, amount, raw_status, frozen,
                 created_at, tx_hash, sender_id, provider_id,
                 sender_name, provider_name) = row

                s_display = sender_name.strip() if sender_name and sender_name.strip() else f"USR-{sender_id}"
                p_display = provider_name.strip() if provider_name and provider_name.strip() else f"PRV-{provider_id}"
                raw_norm = (raw_status or 'On Hold').strip()
                display_status = status_map.get(raw_norm.lower(), raw_norm.title())
                if frozen is True:
                    display_status = 'Frozen'

                escrow_list.append({
                    'id': f"EID{escrow_id}",
                    'raw_id': escrow_id,
                    'delivery_id': delivery_id,
                    'sender_id': f"{s_display} (ID: {sender_id})",
                    'provider_id': f"{p_display} (ID: {provider_id})",
                    'amount': f"₱{float(amount or 0):,.2f}",
                    'escrow_status': display_status,
                    'bc_escrow_tx_hash': tx_hash or '',
                    'emergency_frozen': bool(frozen),
                    'created_at': created_at.strftime('%Y-%m-%d %I:%M %p') if created_at else '—',
                })

            cursor.execute("""
                SELECT
                    t.transaction_id, t.escrow_id, ep.delivery_id,
                    t.base_amount, t.service_fee, t.penalty_fee, t.total_amount,
                    t.payment_method, t.status, t.processed_at
                FROM transactions t
                LEFT JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
                ORDER BY t.processed_at DESC NULLS LAST, t.transaction_id DESC
            """)
            for r in cursor.fetchall():
                (tid, escrow_id, delivery_id,
                 base_amount, service_fee, penalty_fee, total_amount,
                 payment_method, raw_tx_status, processed_at) = r

                normalized_status = status_map.get((raw_tx_status or '').strip().lower(), (raw_tx_status or 'Released').title())

                transactions_list.append({
                    'id': f"TID{tid}",
                    'escrow_id': f"EID{escrow_id}" if escrow_id else '—',
                    'delivery_id': delivery_id or '—',
                    'base_amount': f"₱{float(base_amount or 0):,.2f}",
                    'service_fee': f"₱{float(service_fee or 0):,.2f}",
                    'penalty_fee': f"₱{float(penalty_fee or 0):,.2f}",
                    'total_amount': f"₱{float(total_amount or 0):,.2f}",
                    'method': payment_method or 'GCash',
                    'status': normalized_status,
                    'processed_at': processed_at.strftime('%Y-%m-%d %I:%M %p') if processed_at else '—',
                })

    except Exception as e:
        print(f"[escrow_payments] Database query error: {e}")

    return render(request, 'pages/escrow_payments.html', {
        'current_tab': current_tab,
        'escrow_list': escrow_list,
        'transactions': transactions_list,
    })


@admin_required
@require_POST
def process_escrow_action(request):
    try:
        data = json.loads(request.body)
        escrow_id = str(data.get('escrow_id', '')).replace('EID', '')
        action = data.get('action')

        if action not in ('release', 'refund'):
            return JsonResponse({'error': 'Invalid action'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("SELECT amount, emergency_frozen FROM escrow_payments WHERE escrow_id = %s", [escrow_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'error': 'Escrow record not found'}, status=404)

            escrow_amount, is_frozen = float(row[0] or 0.00), bool(row[1])
            if is_frozen:
                return JsonResponse({'error': 'This escrow account is currently FROZEN. Please unfreeze it first.'}, status=400)

            new_status = 'Released' if action == 'release' else 'Refunded'

            cursor.execute("""
                UPDATE escrow_payments SET escrow_status = %s, emergency_frozen = false
                WHERE escrow_id = %s
            """, [new_status, escrow_id])

            cursor.execute("""
                INSERT INTO transactions
                    (base_amount, service_fee, total_amount, penalty_fee, payment_method, status, processed_at, escrow_id)
                VALUES (%s, 0.00, %s, 0.00, 'GCash', %s, NOW(), %s)
            """, [escrow_amount, escrow_amount, new_status, escrow_id])

        return JsonResponse({'status': 'success', 'new_status': new_status})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@admin_required
@require_POST
def toggle_escrow_freeze(request):
    try:
        data = json.loads(request.body)
        escrow_id = data.get('escrow_id')

        if isinstance(escrow_id, str) and escrow_id.startswith('EID'):
            escrow_id = escrow_id.replace('EID', '')

        with connection.cursor() as cursor:
            cursor.execute("SELECT emergency_frozen FROM escrow_payments WHERE escrow_id = %s", [escrow_id])
            row = cursor.fetchone()

            if not row:
                return JsonResponse({'error': 'Escrow record not found'}, status=404)

            is_currently_frozen = row[0]
            new_frozen_state = not is_currently_frozen
            new_status = 'Frozen' if new_frozen_state else 'On Hold'

            cursor.execute("""
                UPDATE escrow_payments SET emergency_frozen = %s, escrow_status = %s
                WHERE escrow_id = %s
            """, [new_frozen_state, new_status, escrow_id])

        return JsonResponse({
            'status': 'success',
            'is_frozen': new_frozen_state,
            'escrow_status': new_status
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ==========================================
# RATINGS & FEEDBACK
# ==========================================
@admin_required
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
                SELECT review_id, rating, review_text, bc_rating_tx_hash,
                       delivery_id, reviewer_id, reviewee_id, created_at
                FROM ratings_reviews ORDER BY created_at DESC
            """)
            for row in cursor.fetchall():
                item = {
                    'review_id': row[0], 'rating': row[1], 'review_text': row[2],
                    'bc_rating_tx_hash': row[3], 'delivery_id': row[4],
                    'reviewer_id': row[5], 'reviewee_id': row[6],
                    'created_at': row[7].strftime('%Y-%m-%d') if row[7] else '—',
                    'status': 'Flagged' if row[1] <= 2 else 'Active'
                }
                reviews_list.append(item)
                if item['status'] == 'Flagged':
                    disputes_list.append(item)

    except Exception:
        reviews_list = [
            {'review_id': 101, 'rating': 2, 'review_text': 'Package left at wrong location and delayed by 2 hours.', 'bc_rating_tx_hash': '0x8f2...', 'delivery_id': 5001, 'reviewer_id': 301, 'reviewee_id': 402, 'created_at': '2026-03-28', 'status': 'Flagged'},
            {'review_id': 102, 'rating': 1, 'review_text': 'Very unprofessional handler. Item box was dented.', 'bc_rating_tx_hash': '0x1a2...', 'delivery_id': 5002, 'reviewer_id': 302, 'reviewee_id': 403, 'created_at': '2026-03-27', 'status': 'Flagged'},
            {'review_id': 103, 'rating': 5, 'review_text': 'Very careful with my package. Arrived earlier than expected!', 'bc_rating_tx_hash': '0x3c4...', 'delivery_id': 5003, 'reviewer_id': 303, 'reviewee_id': 403, 'created_at': '2026-03-26', 'status': 'Active'},
        ]
        disputes_list = [r for r in reviews_list if r['status'] == 'Flagged']

    return render(request, 'pages/ratings_feedback.html', {
        'current_tab': current_tab,
        'reviews_list': reviews_list,
        'disputes_list': disputes_list,
    })


# ==========================================
# REPORTS
# ==========================================
@admin_required
def reports(request):
    current_tab     = request.GET.get('tab', 'overview')
    selected_period = request.GET.get('period', 'this_month')
    status_filter   = request.GET.get('status', '')

    period_days = {'this_month': 30, 'last_month': 60, 'last_3_months': 90, 'this_year': 365}
    days = period_days.get(selected_period, 30)

    ctx = {
        'current_tab': current_tab, 'selected_period': selected_period,
        'status_filter': status_filter,
        'chart_labels': json.dumps([]), 'overview_delivery_values': json.dumps([]),
        'overview_revenue_values': json.dumps([]), 'net_revenue_values': json.dumps([]),
        'week_labels': json.dumps([]), 'week_completed': json.dumps([]),
        'week_cancelled': json.dumps([]), 'week_pending': json.dumps([]),
        'delivery_type_labels': json.dumps(['Curb-side', 'Door-to-Door']),
        'delivery_type_values': json.dumps([0, 0]),
        'payment_method_labels': json.dumps(['GCash', 'Card', 'Bank Transfer']),
        'payment_method_values': json.dumps([0, 0, 0]),
        'signup_senders': json.dumps([]), 'signup_providers': json.dumps([]),
        'weekly_rows': [], 'top_providers': [], 'recent_transactions': [], 'blockchain_records': [],
        'ov_completed': '0', 'ov_net_revenue': '₱0',
        'ov_fulfillment_rate': '0.0%', 'ov_cancellation_rate': '0.0%',
        'ov_dispute_rate': '0.0%', 'ov_active_users': '0', 'ov_new_users': '0',
        'del_total': '0', 'del_completion': '0.0%', 'del_cancel': '0.0%',
        'del_avg_duration': '0m', 'del_exception': '0.0%',
        'fin_gmv': '₱0', 'fin_net': '₱0', 'fin_take_rate': '0.0%',
        'fin_escrow_held': '₱0', 'fin_refunded': '₱0',
        'usr_new_signups': '0', 'usr_active_senders': '0', 'usr_active_providers': '0',
        'usr_repeat_rate': '0.0%', 'usr_pending_verifications': '0',
        'bc_total_proofs': '0', 'bc_pickup_rate': '0.0%',
        'bc_dropoff_rate': '0.0%', 'bc_escrow_anchored': '0',
    }

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                WITH months AS (
                    SELECT DATE_TRUNC('month', CURRENT_DATE) - (n || ' month')::interval AS m
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT TO_CHAR(m, 'Mon') AS label, m FROM months ORDER BY m
            """)
            month_rows = cursor.fetchall()
            month_labels = [r[0] for r in month_rows]
            month_starts = [r[1] for r in month_rows]
            ctx['chart_labels'] = json.dumps(month_labels)

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
                GROUP BY m ORDER BY m
            """)
            del_by_month = {r[0].replace(day=1): r[1] for r in cursor.fetchall()}
            ctx['overview_delivery_values'] = json.dumps(
                [int(del_by_month.get(m.replace(day=1), 0)) for m in month_starts]
            )

            cursor.execute("""
                SELECT DATE_TRUNC('month', processed_at) AS m,
                       COALESCE(SUM(total_amount), 0) AS total_rev,
                       COALESCE(SUM(service_fee + penalty_fee), 0) AS net_rev
                FROM transactions
                WHERE status IN ('Completed', 'Released')
                  AND processed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                GROUP BY m ORDER BY m
            """)
            rev_by_month = {r[0].replace(day=1): (float(r[1]), float(r[2])) for r in cursor.fetchall()}
            ctx['overview_revenue_values'] = json.dumps(
                [float(rev_by_month.get(m.replace(day=1), (0, 0))[0]) for m in month_starts]
            )
            ctx['net_revenue_values'] = json.dumps(
                [float(rev_by_month.get(m.replace(day=1), (0, 0))[1]) for m in month_starts]
            )

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
                SELECT COALESCE(SUM(service_fee + penalty_fee), 0) FROM transactions
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
                SELECT COUNT(DISTINCT u.user_id) AS active_users,
                       COUNT(*) FILTER (WHERE u.created_at >= CURRENT_DATE - (%s || ' days')::interval) AS new_users
                FROM users u WHERE u.is_active = TRUE
            """, [days])
            row = cursor.fetchone()
            if row:
                ctx['ov_active_users'] = str(int(row[0] or 0))
                ctx['ov_new_users'] = str(int(row[1] or 0))

    except Exception as e:
        print(f"[reports] DB error: {e}")

    return render(request, 'pages/reports.html', ctx)


# ==========================================
# SETTINGS
# ==========================================
@admin_required
def settings_page(request):
    settings_data = {
        'door_to_door': '20.00',
        'platform_commission': '8.5',
        'base_fare': '49.00',
        'per_km_rate': '14.50',
    }

    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                new_door_to_door       = request.POST.get('door_to_door', settings_data['door_to_door'])
                new_platform_commission = request.POST.get('platform_commission', settings_data['platform_commission'])
                new_base_fare          = request.POST.get('base_fare', settings_data['base_fare'])
                new_per_km_rate        = request.POST.get('per_km_rate', settings_data['per_km_rate'])

                cursor.execute("SELECT rate_id FROM delivery_rates ORDER BY updated_at DESC LIMIT 1")
                row = cursor.fetchone()

                if row:
                    cursor.execute("""
                        UPDATE delivery_rates
                        SET small_box_fee = %s, base_rate = %s, per_km_rate = %s, updated_at = NOW()
                        WHERE rate_id = %s
                    """, [float(new_door_to_door or 0), float(new_base_fare or 0), float(new_per_km_rate or 0), row[0]])
                else:
                    cursor.execute("""
                        INSERT INTO delivery_rates
                            (delivery_type, small_box_fee, medium_box_fee, large_box_fee, base_rate, per_km_rate, updated_at)
                        VALUES ('Standard', %s, 0, 0, %s, %s, NOW())
                    """, [float(new_door_to_door or 0), float(new_base_fare or 0), float(new_per_km_rate or 0)])

                request.session['platform_commission'] = new_platform_commission
                messages.success(request, 'Settings updated successfully!')

                settings_data = {
                    'door_to_door': new_door_to_door,
                    'platform_commission': new_platform_commission,
                    'base_fare': new_base_fare,
                    'per_km_rate': new_per_km_rate,
                }
                return render(request, 'pages/settings.html', {'settings': settings_data})

            cursor.execute("""
                SELECT small_box_fee, base_rate, per_km_rate, updated_at
                FROM delivery_rates ORDER BY updated_at DESC LIMIT 1
            """)
            row = cursor.fetchone()

            if row:
                settings_data['door_to_door'] = f"{float(row[0] or 0):.2f}"
                settings_data['base_fare']    = f"{float(row[1] or 0):.2f}"
                settings_data['per_km_rate']  = f"{float(row[2] or 0):.2f}"

            settings_data['platform_commission'] = request.session.get(
                'platform_commission', settings_data['platform_commission']
            )

    except Exception as e:
        print(f"[settings_page] DB error: {e}")

    return render(request, 'pages/settings.html', {'settings': settings_data})


# ==========================================
# LOGOUT
# ==========================================
def custom_logout(request):
    for k in ['is_mock_logged_in', 'admin_first_name', 'admin_last_name', 'admin_email']:
        request.session.pop(k, None)
    return redirect('login')


# ==========================================
# SUPPORT INBOX
# ==========================================
@admin_required
def admin_support_view(request):
    try:
        return render(request, 'pages/admin_support_inbox.html')
    except TemplateDoesNotExist:
        return render(request, 'admin_support_inbox.html')


@admin_required
@require_http_methods(["GET"])
def support_tickets_api(request):
    """
    Return exactly ONE row per user that has any support ticket.
    Picks the most recent root ticket as the representative.
    """
    status = request.GET.get('status', 'open')
    search = (request.GET.get('q') or '').strip()

    with connection.cursor() as cur:
        sql = """
            WITH latest_root AS (
                SELECT DISTINCT ON (user_id)
                    notif_id AS ticket_id,
                    user_id,
                    title    AS subject,
                    is_read,
                    created_at,
                    body
                FROM notification_log
                WHERE type = 'support' AND ref_id IS NULL
                ORDER BY user_id, created_at DESC
            )
            SELECT
                t.ticket_id,
                t.user_id,
                t.subject,
                t.is_read,
                t.created_at,
                u.first_name,
                u.last_name,
                (
                    SELECT r.role_name
                    FROM user_roles ur
                    JOIN roles r ON r.role_id = ur.role_id
                    WHERE ur.user_id = u.user_id
                    ORDER BY ur.role_id ASC
                    LIMIT 1
                ) AS role_name,
                (
                    SELECT body FROM notification_log m
                    WHERE m.ref_id = t.ticket_id
                    ORDER BY m.created_at DESC
                    LIMIT 1
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

    # Mark as 'pending' if there's a newer admin reply
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
            LEFT JOIN locations pl  ON pl.location_id = u.primary_loc_id
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
            'author_name': 'Admin' if is_admin else f"{t[6] or ''} {t[7] or ''}".strip(),
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
            VALUES (%s, 'Support reply', %s, 'support_reply', FALSE, %s)
            RETURNING notif_id, created_at
        """, [user_id, body, ticket_id])
        msg_id, created_at = cur.fetchone()

        cur.execute("UPDATE notification_log SET is_read = TRUE WHERE notif_id = %s", [ticket_id])

    return JsonResponse({
        'message': {
            'id': msg_id, 'body': body, 'is_admin_reply': True,
            'author_name': 'Admin',
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
    """Best-effort admin user id for the direct chat feature."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT u.user_id FROM users u
            JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN roles r ON r.role_id = ur.role_id
            WHERE r.role_name ILIKE 'admin'
            ORDER BY u.user_id LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute("""
            SELECT user_id FROM users
            WHERE email ILIKE 'admin%' OR email ILIKE 'support%'
            ORDER BY user_id LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute("SELECT user_id FROM users ORDER BY user_id LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None


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
            return JsonResponse({'status': 'success', 'room_id': existing[0], 'created': False})

        cur.execute("""
            INSERT INTO chat_rooms (delivery_id, is_support, participant_a, participant_b)
            VALUES (NULL, TRUE, %s, %s)
            RETURNING room_id
        """, [admin_id, target_user_id])
        room_id = cur.fetchone()[0]

    return JsonResponse({'status': 'success', 'room_id': room_id, 'created': True})


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
        if row:
            target_user = row[0]
            cur.execute("""
                INSERT INTO notification_log (user_id, title, body, type, ref_id)
                VALUES (%s, 'New message from support', %s, 'chat', %s)
            """, [target_user, body[:140], room_id])

    return JsonResponse({'message': {
        'id': msg_id, 'sender_id': admin_id, 'message': body,
        'sent_at': sent_at.isoformat(), 'is_read': False, 'is_admin': True,
    }})