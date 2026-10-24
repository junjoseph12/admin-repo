# views/reports.py
from django.shortcuts import render
from django.db import connection
import json
from .login import admin_required


@admin_required
def reports(request):
    current_tab     = request.GET.get('tab', 'overview')
    selected_period = request.GET.get('period', 'this_month')
    status_filter   = request.GET.get('status', '')
    proof_type      = request.GET.get('proof_type', '')

    period_days = {
        'this_month': 30,
        'last_month': 60,
        'last_3_months': 90,
        'this_year': 365,
    }
    days = period_days.get(selected_period, 30)
    ADMIN_EMAIL = 'admin@packnship.com'

    ctx = {
        'current_tab': current_tab,
        'selected_period': selected_period,
        'status_filter': status_filter,

        # Chart data
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

        # Table data
        'weekly_rows': [],
        'top_providers': [],
        'recent_transactions': [],
        'blockchain_records': [],

        # Overview KPIs
        'ov_completed': '0',
        'ov_completed_delta': '0.0%',
        'ov_net_revenue': '₱0',
        'ov_net_revenue_delta': '0.0%',
        'ov_fulfillment_rate': '0.0%',
        'ov_cancellation_rate': '0.0%',
        'ov_dispute_rate': '0.0%',
        'ov_active_users': '0',
        'ov_new_users': '0',

        # Delivery KPIs
        'del_total': '0',
        'del_completion': '0.0%',
        'del_cancel': '0.0%',
        'del_avg_duration': '0m',
        'del_exception': '0.0%',

        # Financial KPIs
        'fin_gmv': '₱0',
        'fin_net': '₱0',
        'fin_take_rate': '0.0%',
        'fin_escrow_held': '₱0',
        'fin_refunded': '₱0',

        # User KPIs
        'usr_new_signups': '0',
        'usr_active_senders': '0',
        'usr_active_providers': '0',
        'usr_repeat_rate': '0.0%',
        'usr_pending_verifications': '0',

        # Blockchain KPIs
        'bc_total_anchored': '0',
        'bc_pickup_rate': '0.0%',
        'bc_dropoff_rate': '0.0%',
        'bc_escrow_anchored': '0',
        'bc_tx_anchored': '0',
        'bc_withdrawal_anchored': '0',
    }

    try:
        with connection.cursor() as cursor:

            # ============================================================
            # MONTH LABELS (last 6 months)
            # ============================================================
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

            # ============================================================
            # DELIVERIES PER MONTH (last 6 months)
            # ============================================================
            cursor.execute("""
                SELECT DATE_TRUNC('month', dr.created_at) AS m,
                       COUNT(*) FILTER (WHERE dr.delivery_status = 'Completed') AS completed_cnt
                FROM delivery_requests dr
                WHERE dr.created_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                GROUP BY m ORDER BY m
            """)
            del_by_month = {r[0].replace(day=1): int(r[1] or 0) for r in cursor.fetchall()}
            ctx['overview_delivery_values'] = json.dumps(
                [int(del_by_month.get(m.replace(day=1), 0)) for m in month_starts]
            )

            # ============================================================
            # REVENUE PER MONTH (last 6 months)
            # ============================================================
            cursor.execute("""
                SELECT DATE_TRUNC('month', t.processed_at) AS m,
                       COALESCE(SUM(t.total_amount), 0) AS total_rev,
                       COALESCE(SUM(t.service_fee + t.penalty_fee), 0) AS net_rev
                FROM transactions t
                WHERE t.status IN ('Completed', 'Released')
                  AND t.processed_at IS NOT NULL
                  AND t.processed_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months'
                GROUP BY m ORDER BY m
            """)
            rev_by_month = {r[0].replace(day=1): (float(r[1] or 0), float(r[2] or 0)) for r in cursor.fetchall()}
            ctx['overview_revenue_values'] = json.dumps(
                [float(rev_by_month.get(m.replace(day=1), (0, 0))[0]) for m in month_starts]
            )
            ctx['net_revenue_values'] = json.dumps(
                [float(rev_by_month.get(m.replace(day=1), (0, 0))[1]) for m in month_starts]
            )

            # ============================================================
            # OVERVIEW KPIs
            # ============================================================
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Completed') AS completed_cnt,
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Cancelled') AS cancelled_cnt,
                    COUNT(*) AS total_cnt
                FROM delivery_requests dr
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            completed_cnt = cancelled_cnt = total_cnt = 0
            if row:
                completed_cnt = int(row[0] or 0)
                cancelled_cnt = int(row[1] or 0)
                total_cnt     = int(row[2] or 0)
                ctx['ov_completed'] = str(completed_cnt)
                ctx['ov_fulfillment_rate'] = f"{(completed_cnt / total_cnt * 100):.1f}%" if total_cnt else '0.0%'
                ctx['ov_cancellation_rate'] = f"{(cancelled_cnt / total_cnt * 100):.1f}%" if total_cnt else '0.0%'

            cursor.execute("""
                SELECT COALESCE(SUM(t.service_fee + t.penalty_fee), 0)
                FROM transactions t
                WHERE t.status IN ('Completed', 'Released')
                  AND t.processed_at IS NOT NULL
                  AND t.processed_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            rev = float(cursor.fetchone()[0] or 0)
            ctx['ov_net_revenue'] = f"₱{rev:,.0f}"

            cursor.execute("""
                SELECT COUNT(*) FROM disputes
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            disputes_cnt = int(cursor.fetchone()[0] or 0)
            ctx['ov_dispute_rate'] = f"{(disputes_cnt / completed_cnt * 100):.1f}%" if completed_cnt else '0.0%'

            # Active / new users (Excluding Admin)
            cursor.execute("""
                SELECT COUNT(DISTINCT u.user_id) AS active_users,
                       COUNT(*) FILTER (WHERE u.created_at >= CURRENT_DATE - (%s || ' days')::interval) AS new_users
                FROM users u
                WHERE u.is_active = TRUE
                  AND u.email != %s
            """, [days, ADMIN_EMAIL])
            row = cursor.fetchone()
            if row:
                ctx['ov_active_users'] = str(int(row[0] or 0))
                ctx['ov_new_users']    = str(int(row[1] or 0))

            # ============================================================
            # DELIVERIES TAB KPIs
            # ============================================================
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_cnt,
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Completed') AS completed_cnt,
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Cancelled') AS cancelled_cnt
                FROM delivery_requests dr
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            if row:
                tot, comp, canc = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
                ctx['del_total'] = str(tot)
                ctx['del_completion'] = f"{(comp / tot * 100):.1f}%" if tot else '0.0%'
                ctx['del_cancel'] = f"{(canc / tot * 100):.1f}%" if tot else '0.0%'

            cursor.execute("""
                SELECT AVG(EXTRACT(EPOCH FROM (d.completed_at - d.accepted_at)) / 60)
                FROM deliveries d
                WHERE d.completed_at IS NOT NULL
                  AND d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            avg_mins = cursor.fetchone()[0]
            if avg_mins is not None:
                mins = float(avg_mins)
                if mins < 60:
                    ctx['del_avg_duration'] = f"{mins:.0f}m"
                elif mins < 1440:
                    ctx['del_avg_duration'] = f"{mins/60:.1f}h"
                else:
                    ctx['del_avg_duration'] = f"{mins/1440:.1f}d"

            cursor.execute("""
                SELECT COUNT(*) FROM delivery_issues
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            issues_cnt = int(cursor.fetchone()[0] or 0)
            ctx['del_exception'] = f"{(issues_cnt / comp * 100):.1f}%" if comp else '0.0%'

            # Weekly rows
            cursor.execute("""
                WITH weeks AS (
                    SELECT DATE_TRUNC('week', CURRENT_DATE) - (n || ' week')::interval AS w
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT
                    TO_CHAR(w.w, 'Mon DD') AS label,
                    w.w AS week_start,
                    COUNT(dr.request_id) AS requests,
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Completed') AS completed_cnt,
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Cancelled') AS cancelled_cnt,
                    COUNT(*) FILTER (WHERE dr.delivery_status IN ('Pending','Accepted','In Transit')) AS pending_cnt,
                    AVG(EXTRACT(EPOCH FROM (d.completed_at - d.accepted_at)) / 60)
                        FILTER (WHERE d.completed_at IS NOT NULL) AS avg_mins
                FROM weeks w
                LEFT JOIN delivery_requests dr
                       ON dr.created_at >= w.w
                      AND dr.created_at <  w.w + INTERVAL '1 week'
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                GROUP BY w.w
                ORDER BY w.w
            """)
            week_labels, week_completed, week_cancelled, week_pending = [], [], [], []
            for r in cursor.fetchall():
                label, _ws, req, comp_w, canc_w, pend_w, avg_m = r
                week_labels.append(label)
                week_completed.append(int(comp_w or 0))
                week_cancelled.append(int(canc_w or 0))
                week_pending.append(int(pend_w or 0))

                duration_str = '—'
                if avg_m is not None:
                    m = float(avg_m)
                    if m < 60:    duration_str = f"{m:.0f}m"
                    elif m < 1440: duration_str = f"{m/60:.1f}h"
                    else:          duration_str = f"{m/1440:.1f}d"

                ctx['weekly_rows'].append({
                    'label': label,
                    'requests': int(req or 0),
                    'completed': int(comp_w or 0),
                    'cancelled': int(canc_w or 0),
                    'duration': duration_str,
                })

            ctx['week_labels']    = json.dumps(week_labels)
            ctx['week_completed'] = json.dumps(week_completed)
            ctx['week_cancelled'] = json.dumps(week_cancelled)
            ctx['week_pending']   = json.dumps(week_pending)

            # Delivery type split
            cursor.execute("""
                SELECT LOWER(dr.pickup_type) AS ptype, COUNT(*)
                FROM delivery_requests dr
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY LOWER(dr.pickup_type)
            """, [days])
            type_map = {r[0]: int(r[1] or 0) for r in cursor.fetchall()}
            curbside = type_map.get('curbside', 0) + type_map.get('curb-side', 0) + type_map.get('curb', 0)
            door     = type_map.get('door', 0) + type_map.get('door-to-door', 0) + type_map.get('door_to_door', 0)
            ctx['delivery_type_values'] = json.dumps([curbside, door])

            # ============================================================
            # FINANCIAL TAB KPIs
            # ============================================================
            cursor.execute("""
                SELECT
                    COALESCE(SUM(t.total_amount), 0) AS gmv,
                    COALESCE(SUM(t.service_fee + t.penalty_fee), 0) AS net
                FROM transactions t
                WHERE t.status IN ('Completed', 'Released')
                  AND t.processed_at IS NOT NULL
                  AND t.processed_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            gmv = float(row[0] or 0)
            net = float(row[1] or 0)
            ctx['fin_gmv'] = f"₱{gmv:,.0f}"
            ctx['fin_net'] = f"₱{net:,.0f}"
            ctx['fin_take_rate'] = f"{(net / gmv * 100):.1f}%" if gmv else '0.0%'

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM escrow_payments
                WHERE LOWER(escrow_status) IN ('on hold', 'on_hold', 'pending', 'frozen')
            """)
            ctx['fin_escrow_held'] = f"₱{float(cursor.fetchone()[0] or 0):,.0f}"

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM escrow_payments
                WHERE LOWER(escrow_status) = 'refunded'
                  AND created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['fin_refunded'] = f"₱{float(cursor.fetchone()[0] or 0):,.0f}"

            # Payment method distribution
            cursor.execute("""
                SELECT LOWER(t.payment_method), COALESCE(SUM(t.total_amount), 0)
                FROM transactions t
                WHERE t.status IN ('Completed', 'Released')
                  AND t.processed_at IS NOT NULL
                  AND t.processed_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY LOWER(t.payment_method)
            """, [days])
            pm_map = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}
            ctx['payment_method_values'] = json.dumps([
                pm_map.get('gcash', 0),
                pm_map.get('card', 0) + pm_map.get('credit card', 0) + pm_map.get('debit card', 0),
                pm_map.get('bank', 0) + pm_map.get('bank transfer', 0) + pm_map.get('bank_transfer', 0),
            ])

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
                WHERE t.processed_at IS NOT NULL
                ORDER BY t.processed_at DESC
                LIMIT 10
            """)
            recent = []
            for r in cursor.fetchall():
                tid, did, amt, pm, st = r
                st_norm = (st or 'Pending').strip()
                if st_norm.lower() in ('completed', 'released'):
                    st_norm = 'Completed'
                elif st_norm.lower() == 'refunded':
                    st_norm = 'Refunded'
                recent.append({
                    'id': f"TID{tid}",
                    'delivery_id': did or '—',
                    'amount': f"₱{float(amt or 0):,.2f}",
                    'method': pm or 'GCash',
                    'status': st_norm,
                })
            ctx['recent_transactions'] = recent

            # ============================================================
            # USERS TAB KPIs
            # ============================================================
            # New signups (Excluding Admin)
            cursor.execute("""
                SELECT COUNT(*) FROM users
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
                  AND email != %s
            """, [days, ADMIN_EMAIL])
            ctx['usr_new_signups'] = str(int(cursor.fetchone()[0] or 0))

            cursor.execute("""
                SELECT COUNT(DISTINCT dr.sender_id)
                FROM delivery_requests dr
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['usr_active_senders'] = str(int(cursor.fetchone()[0] or 0))

            cursor.execute("""
                SELECT COUNT(DISTINCT d.provider_id)
                FROM deliveries d
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['usr_active_providers'] = str(int(cursor.fetchone()[0] or 0))

            # Repeat booking rate
            cursor.execute("""
                WITH per_sender AS (
                    SELECT dr.sender_id, COUNT(*) AS c
                    FROM delivery_requests dr
                    WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
                    GROUP BY dr.sender_id
                )
                SELECT
                    COUNT(*) FILTER (WHERE c >= 2) AS repeat_cnt,
                    COUNT(*) AS total_cnt
                FROM per_sender
            """, [days])
            row = cursor.fetchone()
            if row:
                rep, tot = int(row[0] or 0), int(row[1] or 0)
                ctx['usr_repeat_rate'] = f"{(rep / tot * 100):.1f}%" if tot else '0.0%'

            cursor.execute("""
                SELECT COUNT(*) FROM provider_verifications
                WHERE COALESCE(verification_status, 'Pending') = 'Pending'
            """)
            ctx['usr_pending_verifications'] = str(int(cursor.fetchone()[0] or 0))

            # Signups per month — senders vs providers (Excluding Admin)
            cursor.execute("""
                WITH months AS (
                    SELECT DATE_TRUNC('month', CURRENT_DATE) - (n || ' month')::interval AS m
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT
                    m.m AS month_start,
                    COUNT(*) FILTER (WHERE LOWER(r.role_name) = 'sender')   AS senders,
                    COUNT(*) FILTER (WHERE LOWER(r.role_name) = 'provider') AS providers
                FROM months m
                LEFT JOIN users u
                       ON DATE_TRUNC('month', u.created_at) = m.m
                      AND u.email != %s
                LEFT JOIN user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN roles r       ON r.role_id  = ur.role_id
                GROUP BY m.m ORDER BY m.m
            """, [ADMIN_EMAIL])
            senders_series, providers_series = [], []
            for r in cursor.fetchall():
                senders_series.append(int(r[1] or 0))
                providers_series.append(int(r[2] or 0))
            ctx['signup_senders']   = json.dumps(senders_series)
            ctx['signup_providers'] = json.dumps(providers_series)

            # Top providers this period
            cursor.execute("""
                SELECT
                    u.user_id,
                    COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '') AS name,
                    COUNT(*) FILTER (WHERE dr.delivery_status = 'Completed') AS completed_cnt,
                    COALESCE(AVG(rr.rating), 0) AS avg_rating,
                    COALESCE(SUM(ep.amount) FILTER (WHERE LOWER(ep.escrow_status) IN ('released','completed')), 0) AS earnings
                FROM deliveries d
                JOIN delivery_requests dr ON dr.request_id = d.request_id
                JOIN users u ON u.user_id = d.provider_id
                LEFT JOIN ratings_reviews rr ON rr.reviewee_id = u.user_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY u.user_id, u.first_name, u.last_name
                ORDER BY completed_cnt DESC, earnings DESC
                LIMIT 5
            """, [days])
            for r in cursor.fetchall():
                ctx['top_providers'].append({
                    'name': (r[1] or f"USR-{r[0]}").strip(),
                    'completed': int(r[2] or 0),
                    'rating': f"{float(r[3] or 0):.1f}",
                    'earnings': f"₱{float(r[4] or 0):,.0f}",
                })

            # ============================================================
            # BLOCKCHAIN AUDIT TAB (Matches Ledger)
            # ============================================================
            
            # 1. Base stats for top KPI cards
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE pickup_verified)  AS pickup_ok,
                    COUNT(*) FILTER (WHERE dropoff_verified) AS dropoff_ok
                FROM qr_verifications qr
                JOIN deliveries d ON d.delivery_id = qr.delivery_id
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            qr_total = qr_pickup = qr_dropoff = 0
            if row:
                qr_total   = int(row[0] or 0)
                qr_pickup  = int(row[1] or 0)
                qr_dropoff = int(row[2] or 0)
            ctx['bc_pickup_rate']  = f"{(qr_pickup / qr_total * 100):.1f}%" if qr_total else '0.0%'
            ctx['bc_dropoff_rate'] = f"{(qr_dropoff / qr_total * 100):.1f}%" if qr_total else '0.0%'

            cursor.execute("""
                SELECT COUNT(*) FROM escrow_payments
                WHERE bc_escrow_tx_hash IS NOT NULL AND bc_escrow_tx_hash <> ''
                  AND created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['bc_escrow_anchored'] = str(int(cursor.fetchone()[0] or 0))

            cursor.execute("""
                SELECT COUNT(*) FROM transactions
                WHERE bc_tx_hash IS NOT NULL AND bc_tx_hash <> ''
                  AND COALESCE(processed_at, CURRENT_TIMESTAMP) >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['bc_tx_anchored'] = str(int(cursor.fetchone()[0] or 0))

            cursor.execute("""
                SELECT COUNT(*) FROM withdrawal_requests
                WHERE bc_tx_hash IS NOT NULL AND bc_tx_hash <> ''
                  AND COALESCE(processed_at, requested_at) >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['bc_withdrawal_anchored'] = str(int(cursor.fetchone()[0] or 0))

            # 2. The Unified Query matching the Ledger
            query = """
                SELECT * FROM (
                    -- Deliveries
                    SELECT 'deliveries' AS category, 'Delivery Log' AS badge, 'DEL-' || bl.delivery_id::text AS ref_id, 
                           COALESCE(u.first_name || ' ' || u.last_name, 'Delivery #' || bl.delivery_id) AS entity_name,
                           'Blockchain Log #' || bl.id || ' · Delivery #' || bl.delivery_id AS details,
                           bl.tx_hash, COALESCE(bl.status, 'Confirmed') AS status, bl.created_at AS recorded_at
                    FROM blockchain_logs bl
                    LEFT JOIN deliveries d ON d.delivery_id = bl.delivery_id
                    LEFT JOIN users u ON u.user_id = d.provider_id

                    UNION ALL

                    -- Provider KYC
                    SELECT 'verifications' AS category, 'Provider KYC' AS badge, 'US' || pv.provider_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Provider US' || pv.provider_id) AS entity_name,
                           'License: ' || pv.drivers_license_number || ' (' || pv.verification_status || ')' AS details,
                           pv.bc_verif_tx_hash AS tx_hash, 'Confirmed' AS status, COALESCE(pv.verified_at, pv.submitted_at) AS recorded_at
                    FROM provider_verifications pv
                    JOIN users u ON u.user_id = pv.provider_id
                    WHERE pv.bc_verif_tx_hash IS NOT NULL AND pv.bc_verif_tx_hash <> ''

                    UNION ALL

                    -- Escrow
                    SELECT 'escrow' AS category, 'Escrow Payment' AS badge, 'ESC-' || ep.escrow_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Escrow #' || ep.escrow_id) AS entity_name,
                           '₱' || ep.amount || ' · ' || ep.escrow_status || ' (Delivery #' || ep.delivery_id || ')' AS details,
                           ep.bc_escrow_tx_hash AS tx_hash, 'Confirmed' AS status, ep.created_at AS recorded_at
                    FROM escrow_payments ep
                    LEFT JOIN users u ON u.user_id = ep.sender_id
                    WHERE ep.bc_escrow_tx_hash IS NOT NULL AND ep.bc_escrow_tx_hash <> ''

                    UNION ALL

                    -- QR Pickup
                    SELECT 'qr' AS category, 'QR Pickup' AS badge, 'QR-' || qr.qr_id::text || '-P' AS ref_id,
                           'Delivery #' || qr.delivery_id || ' Pickup' AS entity_name,
                           'QR Handoff #' || qr.qr_id || ' · Pickup Verified' AS details,
                           qr.bc_pickup_tx_hash AS tx_hash, 'Confirmed' AS status, d.accepted_at AS recorded_at
                    FROM qr_verifications qr
                    JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE qr.bc_pickup_tx_hash IS NOT NULL AND qr.bc_pickup_tx_hash <> ''

                    UNION ALL

                    -- QR Dropoff
                    SELECT 'qr' AS category, 'QR Dropoff' AS badge, 'QR-' || qr.qr_id::text || '-D' AS ref_id,
                           'Delivery #' || qr.delivery_id || ' Dropoff' AS entity_name,
                           'QR Handoff #' || qr.qr_id || ' · Dropoff Verified' AS details,
                           qr.bc_dropoff_tx_hash AS tx_hash, 'Confirmed' AS status, d.completed_at AS recorded_at
                    FROM qr_verifications qr
                    JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE qr.bc_dropoff_tx_hash IS NOT NULL AND qr.bc_dropoff_tx_hash <> ''

                    UNION ALL

                    -- Reviews
                    SELECT 'reviews' AS category, 'Rating & Review' AS badge, 'REV-' || rr.review_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Review #' || rr.review_id) AS entity_name,
                           '★ ' || rr.rating || '/5 · Delivery #' || rr.delivery_id AS details,
                           rr.bc_rating_tx_hash AS tx_hash, 'Confirmed' AS status, rr.created_at AS recorded_at
                    FROM ratings_reviews rr
                    LEFT JOIN users u ON u.user_id = rr.reviewee_id
                    WHERE rr.bc_rating_tx_hash IS NOT NULL AND rr.bc_rating_tx_hash <> ''

                    UNION ALL

                    -- Financial Transactions
                    SELECT 'transactions' AS category, 'Financial Tx' AS badge, 'TXN-' || t.transaction_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Transaction #' || t.transaction_id) AS entity_name,
                           '₱' || t.total_amount || ' via ' || t.payment_method || ' (' || t.status || ') · Escrow #' || t.escrow_id AS details,
                           t.bc_tx_hash AS tx_hash, 'Confirmed' AS status, COALESCE(t.processed_at, CURRENT_TIMESTAMP) AS recorded_at
                    FROM transactions t
                    JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
                    LEFT JOIN users u ON u.user_id = ep.sender_id
                    WHERE t.bc_tx_hash IS NOT NULL AND t.bc_tx_hash <> ''

                    UNION ALL

                    -- Withdrawals
                    SELECT 'withdrawals' AS category, 'Withdrawal' AS badge, 'WDR-' || w.withdrawal_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Withdrawal #' || w.withdrawal_id) AS entity_name,
                           '₱' || w.amount || ' via ' || w.method || ' (' || w.status || ')' AS details,
                           w.bc_tx_hash AS tx_hash, 'Confirmed' AS status, COALESCE(w.processed_at, w.requested_at) AS recorded_at
                    FROM withdrawal_requests w
                    JOIN provider_wallet pw ON pw.wallet_id = w.provider_wallet_id
                    LEFT JOIN users u ON u.user_id = pw.provider_id
                    WHERE w.bc_tx_hash IS NOT NULL AND w.bc_tx_hash <> ''
                ) sub
                WHERE recorded_at >= CURRENT_DATE - (%s || ' days')::interval
            """
            params = [days]
            
            # Apply the dropdown filter
            if proof_type and proof_type != 'all':
                query += " AND category = %s"
                params.append(proof_type)
            
            query += " ORDER BY recorded_at DESC NULLS LAST LIMIT 50"
            
            cursor.execute(query, params)
            
            records = []
            for r in cursor.fetchall():
                cat, badge, ref_id, entity_name, details, txh, status, rec_at = r
                
                # Match colors from the Ledger page
                color = 'orange'
                if badge == 'Provider KYC': color = 'green'
                elif badge == 'Escrow Payment': color = 'blue'
                elif 'QR' in badge: color = 'purple'
                elif badge == 'Rating & Review': color = 'amber'
                elif badge == 'Financial Tx': color = 'blue'
                elif badge == 'Withdrawal': color = 'purple'

                records.append({
                    'category': cat,
                    'badge': badge,
                    'badge_color': color,
                    'ref_id': ref_id,
                    'entity_name': entity_name,
                    'details': details,
                    'tx_hash': txh or '',
                    'status': status,
                    'timestamp': rec_at.strftime('%b %d, %Y %I:%M %p') if rec_at else '—',
                })
            ctx['blockchain_records'] = records
            ctx['bc_total_anchored'] = str(len(records)) 

    except Exception as e:
        print(f"[reports] DB error: {e}")

    return render(request, 'pages/reports.html', ctx)