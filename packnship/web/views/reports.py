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

    period_days = {
        'this_month': 30,
        'last_month': 60,
        'last_3_months': 90,
        'this_year': 365,
    }
    days = period_days.get(selected_period, 30)

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
        'bc_total_proofs': '0',
        'bc_pickup_rate': '0.0%',
        'bc_dropoff_rate': '0.0%',
        'bc_escrow_anchored': '0',
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
            # DELIVERIES PER MONTH (last 6 months) — for overview chart
            # ============================================================
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
            # Completed / cancelled / total in period
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
            completed_cnt = cancelled_cnt = total_cnt = 0
            if row:
                completed_cnt = int(row[0] or 0)
                cancelled_cnt = int(row[1] or 0)
                total_cnt     = int(row[2] or 0)
                ctx['ov_completed'] = str(completed_cnt)
                ctx['ov_fulfillment_rate'] = f"{(completed_cnt / total_cnt * 100):.1f}%" if total_cnt else '0.0%'
                ctx['ov_cancellation_rate'] = f"{(cancelled_cnt / total_cnt * 100):.1f}%" if total_cnt else '0.0%'

            # Net revenue
            cursor.execute("""
                SELECT COALESCE(SUM(t.service_fee + t.penalty_fee), 0)
                FROM transactions t
                WHERE t.status IN ('Completed', 'Released')
                  AND t.processed_at IS NOT NULL
                  AND t.processed_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            rev = float(cursor.fetchone()[0] or 0)
            ctx['ov_net_revenue'] = f"₱{rev:,.0f}"

            # Dispute rate (use disputes table)
            cursor.execute("""
                SELECT COUNT(*) FROM disputes
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            disputes_cnt = int(cursor.fetchone()[0] or 0)
            ctx['ov_dispute_rate'] = f"{(disputes_cnt / completed_cnt * 100):.1f}%" if completed_cnt else '0.0%'

            # Active / new users
            cursor.execute("""
                SELECT COUNT(DISTINCT u.user_id) AS active_users,
                       COUNT(*) FILTER (WHERE u.created_at >= CURRENT_DATE - (%s || ' days')::interval) AS new_users
                FROM users u
                WHERE u.is_active = TRUE
            """, [days])
            row = cursor.fetchone()
            if row:
                ctx['ov_active_users'] = str(int(row[0] or 0))
                ctx['ov_new_users']    = str(int(row[1] or 0))

            # ============================================================
            # DELIVERIES TAB KPIs
            # ============================================================
            cursor.execute("""
                WITH latest_status AS (
                    SELECT DISTINCT ON (delivery_id) delivery_id, status
                    FROM delivery_status_history
                    ORDER BY delivery_id, updated_at DESC
                )
                SELECT
                    COUNT(*) AS total_cnt,
                    COUNT(*) FILTER (WHERE ls.status = 'Completed') AS completed_cnt,
                    COUNT(*) FILTER (WHERE ls.status = 'Cancelled') AS cancelled_cnt
                FROM deliveries d
                LEFT JOIN latest_status ls ON ls.delivery_id = d.delivery_id
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            if row:
                tot, comp, canc = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
                ctx['del_total'] = str(tot)
                ctx['del_completion'] = f"{(comp / tot * 100):.1f}%" if tot else '0.0%'
                ctx['del_cancel'] = f"{(canc / tot * 100):.1f}%" if tot else '0.0%'

            # Avg fulfillment duration (accepted → completed)
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

            # Exception rate (delivery issues / completed)
            cursor.execute("""
                SELECT COUNT(*) FROM delivery_issues
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            issues_cnt = int(cursor.fetchone()[0] or 0)
            ctx['del_exception'] = f"{(issues_cnt / comp * 100):.1f}%" if comp else '0.0%'

            # Weekly rows (last 6 weeks) — completed / cancelled / pending
            cursor.execute("""
                WITH weeks AS (
                    SELECT DATE_TRUNC('week', CURRENT_DATE) - (n || ' week')::interval AS w
                    FROM generate_series(5, 0, -1) AS n
                ),
                latest_status AS (
                    SELECT DISTINCT ON (delivery_id) delivery_id, status
                    FROM delivery_status_history
                    ORDER BY delivery_id, updated_at DESC
                )
                SELECT
                    TO_CHAR(w.w, 'Mon DD') AS label,
                    w.w AS week_start,
                    COUNT(d.delivery_id) AS requests,
                    COUNT(*) FILTER (WHERE ls.status = 'Completed') AS completed_cnt,
                    COUNT(*) FILTER (WHERE ls.status = 'Cancelled') AS cancelled_cnt,
                    COUNT(*) FILTER (WHERE ls.status IN ('Pending','Accepted','In Transit')) AS pending_cnt,
                    AVG(EXTRACT(EPOCH FROM (d.completed_at - d.accepted_at)) / 60)
                        FILTER (WHERE d.completed_at IS NOT NULL) AS avg_mins
                FROM weeks w
                LEFT JOIN deliveries d
                       ON d.accepted_at >= w.w
                      AND d.accepted_at <  w.w + INTERVAL '1 week'
                LEFT JOIN latest_status ls ON ls.delivery_id = d.delivery_id
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

            # Delivery type split (curb-side vs door-to-door)
            cursor.execute("""
                SELECT LOWER(dr.pickup_type) AS ptype, COUNT(*)
                FROM deliveries d
                JOIN delivery_requests dr ON dr.request_id = d.request_id
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
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

            # Escrow on hold
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM escrow_payments
                WHERE LOWER(escrow_status) IN ('on hold', 'on_hold', 'pending', 'frozen')
            """)
            ctx['fin_escrow_held'] = f"₱{float(cursor.fetchone()[0] or 0):,.0f}"

            # Refunded
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

            # Recent transactions (last 10)
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
                # Normalize status to match the template's conditions
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
            cursor.execute("""
                SELECT COUNT(*) FROM users
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['usr_new_signups'] = str(int(cursor.fetchone()[0] or 0))

            # Active senders (have at least one delivery request in period)
            cursor.execute("""
                SELECT COUNT(DISTINCT dr.sender_id)
                FROM delivery_requests dr
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['usr_active_senders'] = str(int(cursor.fetchone()[0] or 0))

            # Active providers (accepted at least one delivery in period)
            cursor.execute("""
                SELECT COUNT(DISTINCT d.provider_id)
                FROM deliveries d
                WHERE d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['usr_active_providers'] = str(int(cursor.fetchone()[0] or 0))

            # Repeat booking rate (senders with >= 2 requests / senders with >= 1)
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

            # Pending verifications
            cursor.execute("""
                SELECT COUNT(*) FROM provider_verifications
                WHERE COALESCE(verification_status, 'Pending') = 'Pending'
            """)
            ctx['usr_pending_verifications'] = str(int(cursor.fetchone()[0] or 0))

            # Signups per month — senders vs providers
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
                LEFT JOIN user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN roles r       ON r.role_id  = ur.role_id
                GROUP BY m.m ORDER BY m.m
            """)
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
                    COUNT(*) FILTER (WHERE dsh.status = 'Completed') AS completed_cnt,
                    COALESCE(AVG(rr.rating), 0) AS avg_rating,
                    COALESCE(SUM(ep.amount) FILTER (WHERE LOWER(ep.escrow_status) IN ('released','completed')), 0) AS earnings
                FROM deliveries d
                JOIN users u ON u.user_id = d.provider_id
                LEFT JOIN LATERAL (
                    SELECT status FROM delivery_status_history
                    WHERE delivery_id = d.delivery_id
                    ORDER BY updated_at DESC LIMIT 1
                ) dsh ON true
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
            # BLOCKCHAIN AUDIT TAB
            # ============================================================
            # Total proofs (QR verifications with at least one confirmed)
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
            ctx['bc_total_proofs'] = str(qr_total)
            ctx['bc_pickup_rate']  = f"{(qr_pickup / qr_total * 100):.1f}%" if qr_total else '0.0%'
            ctx['bc_dropoff_rate'] = f"{(qr_dropoff / qr_total * 100):.1f}%" if qr_total else '0.0%'

            # Escrow tx anchored
            cursor.execute("""
                SELECT COUNT(*) FROM escrow_payments
                WHERE bc_escrow_tx_hash IS NOT NULL
                  AND bc_escrow_tx_hash <> ''
                  AND created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            ctx['bc_escrow_anchored'] = str(int(cursor.fetchone()[0] or 0))

            # Recent on-chain records (QR + escrow, mixed)
            cursor.execute("""
                SELECT * FROM (
                    SELECT
                        d.delivery_id,
                        'Pickup' AS proof_type,
                        qr.bc_pickup_tx_hash AS tx_hash,
                        qr.pickup_verified AS verified,
                        d.accepted_at AS recorded_at
                    FROM qr_verifications qr
                    JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE qr.bc_pickup_tx_hash IS NOT NULL
                      AND qr.bc_pickup_tx_hash <> ''
                      AND d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval

                    UNION ALL

                    SELECT
                        d.delivery_id,
                        'Drop-off' AS proof_type,
                        qr.bc_dropoff_tx_hash AS tx_hash,
                        qr.dropoff_verified AS verified,
                        d.completed_at AS recorded_at
                    FROM qr_verifications qr
                    JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE qr.bc_dropoff_tx_hash IS NOT NULL
                      AND qr.bc_dropoff_tx_hash <> ''
                      AND d.accepted_at >= CURRENT_DATE - (%s || ' days')::interval

                    UNION ALL

                    SELECT
                        ep.delivery_id,
                        'Escrow' AS proof_type,
                        ep.bc_escrow_tx_hash AS tx_hash,
                        TRUE AS verified,
                        ep.created_at AS recorded_at
                    FROM escrow_payments ep
                    WHERE ep.bc_escrow_tx_hash IS NOT NULL
                      AND ep.bc_escrow_tx_hash <> ''
                      AND ep.created_at >= CURRENT_DATE - (%s || ' days')::interval
                ) t
                ORDER BY recorded_at DESC NULLS LAST
                LIMIT 15
            """, [days, days, days])
            records = []
            for r in cursor.fetchall():
                did, ptype, txh, _ver, rec_at = r
                records.append({
                    'delivery_id': did or '—',
                    'proof_type': ptype,
                    'tx_hash': txh or '',
                    'recorded_at': rec_at.strftime('%Y-%m-%d %H:%M') if rec_at else '—',
                })
            ctx['blockchain_records'] = records

    except Exception as e:
        print(f"[reports] DB error: {e}")

    return render(request, 'pages/reports.html', ctx)