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
    return render(request, 'pages/dashboard.html')


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

    mock_deliveries = [
        {
            'id': '1001',
            'sender': 'Jonel Jumawan',
            'provider': 'Jun Joseph Pestaño',
            'status': 'Pending',
            'emergency': 'Normal',
            'escrow_status': 'On Hold'
        },
        {
            'id': '1002',
            'sender': 'Kornel Jumao-as',
            'provider': 'Jun Joseph Pestaño',
            'status': 'Accepted',
            'emergency': 'Frozen',
            'escrow_status': 'Frozen'
        },
        {
            'id': '1003',
            'sender': 'Alucard Jungler',
            'provider': 'Moises Padriga',
            'status': 'In Transit',
            'emergency': 'Normal',
            'escrow_status': 'On Hold'
        },
        {
            'id': '1004',
            'sender': 'Hilda Roamer',
            'provider': 'Moises Padriga',
            'status': 'Completed',
            'emergency': 'Normal',
            'escrow_status': 'Released'
        },
    ]

    return render(request, 'pages/deliveries.html', {
        'deliveries': mock_deliveries
    })


def generic_admin_page(request, title):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')
    return render(request, 'pages/generic_placeholder.html', {'page_title': title})


def escrow_payments(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    current_tab = request.GET.get('tab', 'active')

    mock_escrow_list = [
        {
            'id': 'EID501',
            'delivery_id': '1001',
            'sender_id': 'USR-201',
            'provider_id': 'PRV-501',
            'amount': '₱250.00',
            'status': 'On Hold',
            'bc_escrow_tx_hash': '0x71c...a89f',
            'emergency_frozen': False,
            'created_at': '2026-03-28 10:15 AM'
        },
        {
            'id': 'EID502',
            'delivery_id': '1002',
            'sender_id': 'USR-204',
            'provider_id': 'PRV-503',
            'amount': '₱180.00',
            'status': 'Frozen',
            'bc_escrow_tx_hash': '0x32b...f11e',
            'emergency_frozen': True,
            'created_at': '2026-03-27 02:40 PM'
        },
        {
            'id': 'EID503',
            'delivery_id': '1003',
            'sender_id': 'USR-210',
            'provider_id': 'PRV-508',
            'amount': '₱220.00',
            'status': 'Released',
            'bc_escrow_tx_hash': '0x88f...c401',
            'emergency_frozen': False,
            'created_at': '2026-03-26 09:10 AM'
        },
    ]

    mock_transactions = [
        {
            'id': 'TID101',
            'escrow_id': 'EID501',
            'delivery_id': '1001',
            'base_amount': '₱200.00',
            'service_fee': '₱30.00',
            'penalty_fee': '₱20.00',
            'total_amount': '₱250.00',
            'method': 'GCash',
            'status': 'On Hold',
            'processed_at': '2026-03-28 10:16 AM'
        },
        {
            'id': 'TID102',
            'escrow_id': 'EID502',
            'delivery_id': '1002',
            'base_amount': '₱150.00',
            'service_fee': '₱30.00',
            'penalty_fee': '₱0.00',
            'total_amount': '₱180.00',
            'method': 'GCash',
            'status': 'Frozen',
            'processed_at': '2026-03-27 02:42 PM'
        },
        {
            'id': 'TID103',
            'escrow_id': 'EID503',
            'delivery_id': '1003',
            'base_amount': '₱190.00',
            'service_fee': '₱30.00',
            'penalty_fee': '₱0.00',
            'total_amount': '₱220.00',
            'method': 'GCash',
            'status': 'Completed',
            'processed_at': '2026-03-26 09:12 AM'
        },
    ]

    return render(request, 'pages/escrow_payments.html', {
        'current_tab': current_tab,
        'escrow_list': mock_escrow_list,
        'transactions': mock_transactions,
    })


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

    current_tab = request.GET.get('tab', 'overview')
    selected_period = request.GET.get('period', 'this_month')

    delivery_type = request.GET.get('delivery_type', '')
    status_filter = request.GET.get('status', '')
    payment_method = request.GET.get('payment_method', '')
    role_filter = request.GET.get('role', '')
    proof_type = request.GET.get('proof_type', '')

    base_completed = 96
    base_net_revenue = 22780
    base_gmv = 152400
    base_total_req = 128

    period_multiplier = 1.0
    if selected_period == 'last_month':
        period_multiplier = 0.88
    elif selected_period == 'last_3_months':
        period_multiplier = 2.75
    elif selected_period == 'this_year':
        period_multiplier = 11.2

    active_filters = sum(1 for f in [delivery_type, status_filter, payment_method, role_filter, proof_type] if f)
    filter_factor = (0.75 ** active_filters) if active_filters > 0 else 1.0

    comp_deliveries = int(base_completed * period_multiplier * filter_factor)
    net_rev = int(base_net_revenue * period_multiplier * filter_factor)
    gmv = int(base_gmv * period_multiplier * filter_factor)
    total_req = int(base_total_req * period_multiplier * filter_factor)

    revenue_data = {
        'labels': ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'],
        'gross_transactions': [int(82000 * period_multiplier), int(94500 * period_multiplier), int(108200 * period_multiplier), int(121400 * period_multiplier), int(138900 * period_multiplier), gmv],
        'net_revenue': [int(12400 * period_multiplier), int(14100 * period_multiplier), int(16800 * period_multiplier), int(18900 * period_multiplier), int(21600 * period_multiplier), net_rev]
    }

    context = {
        'current_tab': current_tab,
        'selected_period': selected_period,
        'delivery_type': delivery_type,
        'status_filter': status_filter,
        'payment_method': payment_method,
        'role_filter': role_filter,
        'proof_type': proof_type,
        'revenue_json': json.dumps(revenue_data),
        'ov_completed': str(comp_deliveries),
        'ov_net_revenue': f"₱{net_rev:,}",
        'del_total': str(total_req),
        'fin_gmv': f"₱{gmv:,}",
        'fin_net': f"₱{net_rev:,}",
    }

    return render(request, 'pages/reports.html', context)


def settings_page(request):
    if not request.session.get('is_mock_logged_in'):
        return redirect('login')

    settings_data = {
        'door_to_door': '20.00',
        'platform_commission': '8.5',
        'base_fare': '49.00',
        'per_km_rate': '14.50'
    }

    if request.method == 'POST':
        settings_data['door_to_door'] = request.POST.get('door_to_door', settings_data['door_to_door'])
        settings_data['platform_commission'] = request.POST.get('platform_commission', settings_data['platform_commission'])
        settings_data['base_fare'] = request.POST.get('base_fare', settings_data['base_fare'])
        settings_data['per_km_rate'] = request.POST.get('per_km_rate', settings_data['per_km_rate'])

        messages.success(request, 'Settings updated successfully!')

    return render(request, 'pages/settings.html', {
        'settings': settings_data
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