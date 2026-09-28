from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
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

    mock_verifications = [
        {
            'id': 1,
            'name': 'John David Torres Villanueva',
            'id_photo': '/media/verifications/ids/sample1.jpg',
            'selfie': '/media/verifications/selfies/sample1.jpg',
            'plate_no': 'ABCD-123',
            'vehicle_type': 'Sedan',
            'vehicle_doc': '/media/verifications/docs/orcr_john.pdf',
            'vehicle_doc_name': 'orcr_john.pdf',
            'status': 'Pending'
        },
        {
            'id': 2,
            'name': 'Bryan Nikole Dionson',
            'id_photo': '/media/verifications/ids/sample2.jpg',
            'selfie': '/media/verifications/selfies/sample2.jpg',
            'plate_no': 'EFGH-456',
            'vehicle_type': 'SUV',
            'vehicle_doc': '/media/verifications/docs/orcr_bryan.pdf',
            'vehicle_doc_name': 'orcr_bryan.pdf',
            'status': 'Pending'
        }
    ]

    return render(request, 'pages/provider_verification.html', {
        'verifications': mock_verifications
    })


def approve_provider(request, pk):
    if request.method == 'POST':
        verification = get_object_or_404(ProviderVerification, pk=pk)
        verification.status = 'Approved'
        verification.save()
    return redirect('provider_verification')


def reject_provider(request, pk):
    if request.method == 'POST':
        verification = get_object_or_404(ProviderVerification, pk=pk)
        verification.status = 'Rejected'
        verification.save()
    return redirect('provider_verification')


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

    escrow_list = []
    transactions_list = []

    try:
        with connection.cursor() as cursor:
            # 1. Active Escrow Query (Excludes 'Released' / 'Completed' / 'Refunded')
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
                WHERE LOWER(ep.escrow_status) NOT IN ('released', 'completed', 'refunded')
                ORDER BY ep.created_at DESC
            """)
            rows = cursor.fetchall()

            for row in rows:
                (escrow_id, delivery_id, amount, escrow_status, emergency_frozen, 
                 created_at, tx_hash, sender_id, provider_id, sender_name, provider_name) = row

                s_display = sender_name.strip() if sender_name and sender_name.strip() else f"USR-{sender_id}"
                p_display = provider_name.strip() if provider_name and provider_name.strip() else f"PRV-{provider_id}"

                escrow_list.append({
                    'id': f"EID{escrow_id}",
                    'raw_id': escrow_id,
                    'delivery_id': delivery_id,
                    'sender_id': f"{s_display} (ID: {sender_id})",
                    'provider_id': f"{p_display} (ID: {provider_id})",
                    'amount': f"₱{float(amount or 0):,.2f}",
                    'escrow_status': (escrow_status or 'On Hold').title(),
                    'bc_escrow_tx_hash': tx_hash or '',
                    'emergency_frozen': bool(emergency_frozen),
                    'created_at': created_at.strftime('%Y-%m-%d %I:%M %p') if created_at else '—'
                })

            # 2. Transaction History Query (Queries real `transactions` joined with `escrow_payments`)
            cursor.execute("""
                SELECT 
                    COALESCE(t.transaction_id, ep.escrow_id) AS tx_id,
                    ep.escrow_id,
                    ep.delivery_id,
                    ep.amount AS base_amount,
                    COALESCE(t.service_fee, 0.00) AS service_fee,
                    COALESCE(t.penalty_fee, 0.00) AS penalty_fee,
                    COALESCE(t.total_amount, ep.amount) AS total_amount,
                    COALESCE(t.payment_method, 'GCash') AS payment_method,
                    ep.escrow_status,
                    COALESCE(t.processed_at, ep.created_at) AS processed_at
                FROM escrow_payments ep
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                WHERE LOWER(ep.escrow_status) IN ('released', 'completed', 'refunded')
                ORDER BY ep.created_at DESC
            """)
            tx_rows = cursor.fetchall()

            for row in tx_rows:
                (tx_id, escrow_id, delivery_id, base_amt, service_fee, penalty_fee, 
                 total_amt, payment_method, status, processed_at) = row

                transactions_list.append({
                    'id': f"TID{tx_id}",
                    'escrow_id': f"EID{escrow_id}",
                    'delivery_id': delivery_id,
                    'base_amount': f"₱{float(base_amt or 0):,.2f}",
                    'service_fee': f"₱{float(service_fee or 0):,.2f}",
                    'penalty_fee': f"₱{float(penalty_fee or 0):,.2f}",
                    'total_amount': f"₱{float(total_amt or 0):,.2f}",
                    'method': payment_method,
                    'escrow_status': (status or 'Complete').title(),
                    'processed_at': processed_at.strftime('%Y-%m-%d %I:%M %p') if processed_at else '—'
                })

    except Exception as e:
        print(f"[escrow_payments] Database query error: {e}")

    return render(request, 'pages/escrow_payments.html', {
        'current_tab': current_tab,
        'escrow_list': escrow_list,
        'transactions': transactions_list,
    })


@require_POST
def process_escrow_action(request):
    """Handles Release and Refund actions for Escrow records."""
    if not request.session.get('is_mock_logged_in'):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        escrow_id = str(data.get('escrow_id', '')).replace('EID', '')
        action = data.get('action')  # 'release' or 'refund'

        if action not in ('release', 'refund'):
            return JsonResponse({'error': 'Invalid action'}, status=400)

        with connection.cursor() as cursor:
            # Check if escrow exists
            cursor.execute("SELECT amount FROM escrow_payments WHERE escrow_id = %s", [escrow_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'error': 'Escrow record not found'}, status=404)

            escrow_amount = float(row[0] or 0.00)
            new_status = 'Released' if action == 'release' else 'Refunded'

            # 1. Update Escrow Status
            cursor.execute("""
                UPDATE escrow_payments 
                SET escrow_status = %s,
                    emergency_frozen = false
                WHERE escrow_id = %s
            """, [new_status, escrow_id])

            # 2. Insert record into transactions table
            cursor.execute("""
                INSERT INTO transactions 
                    (base_amount, service_fee, total_amount, penalty_fee, payment_method, status, processed_at, escrow_id)
                VALUES 
                    (%s, 0.00, %s, 0.00, 'GCash', %s, NOW(), %s)
            """, [escrow_amount, escrow_amount, new_status, escrow_id])

        return JsonResponse({'status': 'success', 'new_status': new_status})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@require_POST
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


# web/views.py (deliveries view only — add this alongside your other views)
from django.shortcuts import render
from .models import Delivery


def deliveries(request):
    """
    Powers deliveries.html and its detail modal.

    NOTE: as of writing, `deliveries`, `delivery_requests`, `escrow_payments`,
    `qr_verifications`, and `transactions` are all EMPTY in Supabase (0 rows).
    This view will correctly return an empty list and the template will show
    its "No delivery records found" state — that's expected, not a bug, until
    real delivery data exists (via the Sender/Provider apps or manual seed
    inserts).

    Builds a flat dict per delivery matching exactly the data-* attributes
    deliveries.html already reads (see the "NOTE FOR THE VIEW" comments in
    that template) — so no template changes are needed, only this view.
    """
    qs = (
        Delivery.objects
        .select_related(
            'request',
            'request__sender',
            'request__cargo',
            'request__pickup_location',
            'request__dropoff_location',
            'provider',
            'vehicle',
        )
        .prefetch_related('issues','status_history')
        .order_by('-request__created_at')
    )

    rows = []
    for d in qs:
        req = d.request
        cargo = req.cargo
        sender = req.sender
        provider = d.provider
        vehicle = d.vehicle
        pickup = req.pickup_location
        dropoff = req.dropoff_location

        # OneToOne reverse relations raise DoesNotExist if the row doesn't
        # exist yet (e.g. escrow not created until payment is initiated) —
        # getattr with a default sidesteps that without extra queries.
        escrow = getattr(d, 'escrow_payment', None)
        qr = getattr(d, 'qr_verification', None)
        chat_room = getattr(d, 'chat_room', None)
        transaction = getattr(escrow, 'transaction', None) if escrow else None

        # issues is prefetched — .first() here doesn't cost an extra query
        latest_issue = d.issues.all()[0] if d.issues.all() else None

        history_str = ';'.join(
                f"{h.status}|{h.updated_at.strftime('%b %d, %Y %I:%M:%S %p')}"
                for h in d.status_history.all()      # already ordered by updated_at
            )

        rows.append({
            'id': d.delivery_id,
            'sender': sender.full_name(),
            'sender_phone': sender.phone_number or '—',
            'provider': provider.full_name(),
            'provider_vehicle': f"{vehicle.vehicle_type} · {vehicle.plate_number}" if vehicle else '—',
            'status': req.delivery_status,
            'delivery_type': req.pickup_type,
            'chat_room_id': chat_room.room_id if chat_room else '',

            'emergency': latest_issue.description if latest_issue else 'None',
            'emergency_type': latest_issue.issue_type if latest_issue else '',
            'emergency_status': latest_issue.status if latest_issue else '',

            'escrow_status': escrow.escrow_status if escrow else '—',
            'escrow_id': escrow.escrow_id if escrow else '',
            'escrow_amount': escrow.amount if escrow else '0.00',
            'escrow_frozen': escrow.emergency_frozen if escrow else False,
            'escrow_tx_hash': escrow.bc_escrow_tx_hash if escrow else '',

            'pickup_address': pickup.full_address() if pickup else '—',
            'dropoff_address': dropoff.full_address() if dropoff else '—',

            'requested_at': req.created_at,
            'accepted_at': d.accepted_at,
            'eta': d.estimated_eta,
            'completed_at': d.completed_at,

            'pickup_verified': qr.pickup_verified if qr else False,
            'dropoff_verified': qr.dropoff_verified if qr else False,

            'cargo_description': cargo.description if (cargo and cargo.description) else 'No description provided.',
            'cargo_weight': cargo.total_weight_kg if cargo else '—',
            'cargo_dimensions': cargo.dimensions_label() if cargo else '—',
            'box_small': cargo.small_box_qty if cargo else 0,
            'box_medium': cargo.medium_box_qty if cargo else 0,
            'box_large': cargo.large_box_qty if cargo else 0,
            'is_fragile': cargo.is_fragile if cargo else False,
            'cargo_photo': cargo.cargo_pic if cargo else '',

            'base_fee': transaction.base_amount if transaction else '0.00',
            'service_fee': transaction.service_fee if transaction else '0.00',
            'penalty_fee': transaction.penalty_fee if transaction else '0.00',
            'total_amount': transaction.total_amount if transaction else '0.00',
            'payment_method': transaction.payment_method if transaction else '—',
            'payment_status': transaction.status if transaction else '—',
            # transactions has no bc_..._tx_hash column in the real schema —
            # left blank rather than inventing a value. See models.py note.
            'transaction_tx_hash': '',

                  'status_history': history_str,
            'dropoff_lat': dropoff.latitude if dropoff else '',
            'dropoff_lng': dropoff.longitude if dropoff else '',
            # No source for the provider's live position exists yet, so these
            # are intentionally blank — the map then shows only the drop-off
            # pin and says "No provider location received yet". Once the
            # provider app sends location pings, fill these in.
            'provider_lat': '',
            'provider_lng': '',
            'location_updated_at': '',
        })

    return render(request, 'pages/deliveries.html', {'deliveries': rows})