# views/users.py
from django.shortcuts import render
from django.db import connection
from .login import admin_required


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
                    LEFT JOIN LATERAL (
                        SELECT vehicle_type, plate_number, verification_status
                        FROM vehicles
                        WHERE provider_id = u.user_id
                        ORDER BY vehicle_id ASC LIMIT 1
                    ) v ON true
                    LEFT JOIN LATERAL (
                        SELECT verification_status
                        FROM provider_verifications
                        WHERE provider_id = u.user_id
                        ORDER BY submitted_at DESC NULLS LAST LIMIT 1
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
                        u.user_id, u.first_name, u.middle_name, u.last_name,
                        u.email, u.phone_number, u.is_verified, u.is_active, u.created_at,
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