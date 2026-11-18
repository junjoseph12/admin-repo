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
    delivery_type   = request.GET.get('delivery_type', '')
    payment_method  = request.GET.get('payment_method', '')
    role_filter     = request.GET.get('role', '')
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
        'payment_method_labels': json.dumps(['GCash', 'Maya']),
        'payment_method_values': json.dumps([0, 0]),
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
            # MONTH LABELS (last 6 months using YYYY-MM string keys)
            # ============================================================
            cursor.execute("""
                WITH months AS (
                    SELECT (DATE_TRUNC('month', CURRENT_TIMESTAMP) - (n || ' month')::interval) AS m
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT TO_CHAR(m, 'Mon') AS label, TO_CHAR(m, 'YYYY-MM') AS ym
                FROM months
                ORDER BY m
            """)
            month_rows = cursor.fetchall()
            month_labels = [r[0] for r in month_rows]
            month_keys   = [r[1] for r in month_rows]
            ctx['chart_labels'] = json.dumps(month_labels)

            # ============================================================
            # DELIVERIES PER MONTH (last 6 months)
            # ============================================================
            cursor.execute("""
                SELECT TO_CHAR(DATE_TRUNC('month', dr.created_at), 'YYYY-MM') AS ym,
                       COUNT(*) AS total_cnt,
                       COUNT(*) FILTER (
                           WHERE LOWER(dr.delivery_status) IN ('completed', 'delivered')
                              OR d.completed_at IS NOT NULL
                       ) AS completed_cnt
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                WHERE dr.created_at >= DATE_TRUNC('month', CURRENT_TIMESTAMP) - INTERVAL '5 months'
                GROUP BY ym
                ORDER BY ym
            """)
            del_by_month = {}
            for ym, tot_c, comp_c in cursor.fetchall():
                # Show completed count if > 0, otherwise total requests so the chart reflects activity
                del_by_month[ym] = int(comp_c or tot_c or 0)

            ctx['overview_delivery_values'] = json.dumps(
                [int(del_by_month.get(k, 0)) for k in month_keys]
            )

            # ============================================================
            # REVENUE PER MONTH (last 6 months)
            # ============================================================
            cursor.execute("""
                SELECT
                    TO_CHAR(DATE_TRUNC('month', COALESCE(t.processed_at, ep.created_at, dr.created_at)), 'YYYY-MM') AS ym,
                    COALESCE(SUM(COALESCE(t.total_amount, ep.amount, dr.estimated_cost, 0)), 0) AS total_rev,
                    COALESCE(SUM(
                        CASE
                            WHEN t.service_fee IS NOT NULL THEN (t.service_fee + COALESCE(t.penalty_fee, 0))
                            ELSE COALESCE(ep.amount, dr.estimated_cost, 0) * 0.10
                        END
                    ), 0) AS net_rev
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                WHERE COALESCE(t.processed_at, ep.created_at, dr.created_at) >= DATE_TRUNC('month', CURRENT_TIMESTAMP) - INTERVAL '5 months'
                  AND LOWER(COALESCE(dr.delivery_status, '')) NOT IN ('cancelled', 'canceled')
                GROUP BY ym
                ORDER BY ym
            """)
            rev_by_month = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in cursor.fetchall()}
            ctx['overview_revenue_values'] = json.dumps(
                [round(rev_by_month.get(k, (0.0, 0.0))[0], 2) for k in month_keys]
            )
            ctx['net_revenue_values'] = json.dumps(
                [round(rev_by_month.get(k, (0.0, 0.0))[1], 2) for k in month_keys]
            )

            # ============================================================
            # OVERVIEW KPIs
            # ============================================================
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('completed', 'delivered')
                           OR d.completed_at IS NOT NULL
                    ) AS completed_cnt,
                    COUNT(*) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('cancelled', 'canceled')
                    ) AS cancelled_cnt,
                    COUNT(*) AS total_cnt
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
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
                SELECT COALESCE(SUM(
                    CASE
                        WHEN t.service_fee IS NOT NULL THEN (t.service_fee + COALESCE(t.penalty_fee, 0))
                        ELSE COALESCE(ep.amount, dr.estimated_cost, 0) * 0.10
                    END
                ), 0)
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                WHERE COALESCE(t.processed_at, ep.created_at, dr.created_at) >= CURRENT_DATE - (%s || ' days')::interval
                  AND LOWER(COALESCE(dr.delivery_status, '')) NOT IN ('cancelled', 'canceled')
            """, [days])
            rev = float(cursor.fetchone()[0] or 0)
            ctx['ov_net_revenue'] = f"₱{rev:,.0f}"

            cursor.execute("""
                SELECT COUNT(*) FROM disputes
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            disputes_cnt = int(cursor.fetchone()[0] or 0)
            denom = completed_cnt if completed_cnt > 0 else total_cnt
            ctx['ov_dispute_rate'] = f"{(disputes_cnt / denom * 100):.1f}%" if denom else '0.0%'

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
            # DELIVERIES TAB KPIs & CHARTS
            # ============================================================
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_cnt,
                    COUNT(*) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('completed', 'delivered')
                           OR d.completed_at IS NOT NULL
                    ) AS completed_cnt,
                    COUNT(*) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('cancelled', 'canceled')
                    ) AS cancelled_cnt
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            row = cursor.fetchone()
            tot = comp = canc = 0
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
                mins = max(0.0, float(avg_mins))
                if mins < 60:
                    ctx['del_avg_duration'] = f"{mins:.0f}m"
                elif mins < 1440:
                    ctx['del_avg_duration'] = f"{mins/60:.1f}h"
                else:
                    ctx['del_avg_duration'] = f"{mins/1440:.1f}d"

            cursor.execute("""
                SELECT COUNT(*) FROM disputes
                WHERE created_at >= CURRENT_DATE - (%s || ' days')::interval
            """, [days])
            issues_cnt = int(cursor.fetchone()[0] or 0)
            denom_del = comp if comp > 0 else tot
            ctx['del_exception'] = f"{(issues_cnt / denom_del * 100):.1f}%" if denom_del else '0.0%'

            # Weekly rows (last 6 weeks)
            cursor.execute("""
                WITH weeks AS (
                    SELECT (DATE_TRUNC('week', CURRENT_TIMESTAMP) - (n || ' week')::interval)::timestamp AS w
                    FROM generate_series(5, 0, -1) AS n
                )
                SELECT
                    TO_CHAR(w.w, 'Mon DD') AS label,
                    w.w AS week_start,
                    COUNT(dr.request_id) AS requests,
                    COUNT(dr.request_id) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('completed', 'delivered')
                           OR d.completed_at IS NOT NULL
                    ) AS completed_cnt,
                    COUNT(dr.request_id) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('cancelled', 'canceled')
                    ) AS cancelled_cnt,
                    COUNT(dr.request_id) FILTER (
                        WHERE LOWER(dr.delivery_status) NOT IN ('completed', 'delivered', 'cancelled', 'canceled')
                          AND d.completed_at IS NULL
                    ) AS pending_cnt,
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
                    m = max(0.0, float(avg_m))
                    if m < 60:     duration_str = f"{m:.0f}m"
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

            # Delivery type split (flexible matching for Curb-side vs Door-to-Door / Express / Standard)
            cursor.execute("""
                SELECT LOWER(COALESCE(dr.pickup_type, '')), COUNT(*)
                FROM delivery_requests dr
                WHERE dr.created_at >= CURRENT_DATE - (%s || ' days')::interval
                GROUP BY LOWER(COALESCE(dr.pickup_type, ''))
            """, [days])
            raw_types = cursor.fetchall()
            curbside = 0
            door = 0
            other_types = {}
            for ptype, cnt in raw_types:
                cnt_val = int(cnt or 0)
                if 'curb' in ptype or 'station' in ptype or 'meetup' in ptype:
                    curbside += cnt_val
                elif 'door' in ptype or 'home' in ptype or 'direct' in ptype:
                    door += cnt_val
                elif ptype:
                    other_types[ptype.title()] = other_types.get(ptype.title(), 0) + cnt_val

            if curbside == 0 and door == 0 and other_types:
                ctx['delivery_type_labels'] = json.dumps(list(other_types.keys()))
                ctx['delivery_type_values'] = json.dumps(list(other_types.values()))
            else:
                ctx['delivery_type_labels'] = json.dumps(['Curb-side', 'Door-to-Door'])
                ctx['delivery_type_values'] = json.dumps([curbside, door])

            # ============================================================
            # FINANCIAL TAB KPIs & CHARTS
            # ============================================================
            cursor.execute("""
                SELECT
                    COALESCE(SUM(COALESCE(t.total_amount, ep.amount, dr.estimated_cost, 0)), 0) AS gmv,
                    COALESCE(SUM(
                        CASE
                            WHEN t.service_fee IS NOT NULL THEN (t.service_fee + COALESCE(t.penalty_fee, 0))
                            ELSE COALESCE(ep.amount, dr.estimated_cost, 0) * 0.10
                        END
                    ), 0) AS net
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                WHERE COALESCE(t.processed_at, ep.created_at, dr.created_at) >= CURRENT_DATE - (%s || ' days')::interval
                  AND LOWER(COALESCE(dr.delivery_status, '')) NOT IN ('cancelled', 'canceled')
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

            # Payment method distribution (GCash vs Maya from transactions & delivery_requests)
            cursor.execute("""
                SELECT
                    LOWER(COALESCE(t.payment_method, dr.payment_provider, 'gcash')) AS pm,
                    COALESCE(SUM(COALESCE(t.total_amount, ep.amount, dr.estimated_cost, 0)), 0) AS amt
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                WHERE COALESCE(t.processed_at, ep.created_at, dr.created_at) >= CURRENT_DATE - (%s || ' days')::interval
                  AND LOWER(COALESCE(dr.delivery_status, '')) NOT IN ('cancelled', 'canceled')
                GROUP BY pm
            """, [days])
            pm_map = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}
            gcash_amt = pm_map.get('gcash', 0.0)
            maya_amt  = pm_map.get('maya', 0.0) + pm_map.get('paymaya', 0.0)
            ctx['payment_method_labels'] = json.dumps(['GCash', 'Maya'])
            ctx['payment_method_values'] = json.dumps([round(gcash_amt, 2), round(maya_amt, 2)])

            # Recent transactions
            cursor.execute("""
                SELECT
                    COALESCE(t.transaction_id, ep.escrow_id, dr.request_id) AS tx_id,
                    COALESCE(ep.delivery_id, d.delivery_id) AS del_id,
                    COALESCE(t.total_amount, ep.amount, dr.estimated_cost, 0) AS amount,
                    COALESCE(t.payment_method, dr.payment_provider, 'GCash') AS method,
                    COALESCE(t.status, ep.escrow_status, dr.payment_status, 'Pending') AS status
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                ORDER BY COALESCE(t.processed_at, ep.created_at, dr.created_at) DESC
                LIMIT 10
            """)
            recent = []
            for r in cursor.fetchall():
                tid, did, amt, pm, st = r
                st_norm = (st or 'Pending').strip()
                if st_norm.lower() in ('completed', 'released', 'paid'):
                    st_norm = 'Completed'
                elif st_norm.lower() == 'refunded':
                    st_norm = 'Refunded'
                else:
                    st_norm = st_norm.title()
                recent.append({
                    'id': f"TID{tid}",
                    'delivery_id': did or '—',
                    'amount': f"₱{float(amt or 0):,.2f}",
                    'method': (pm or 'GCash').upper() if (pm or '').lower() == 'gcash' else (pm or 'GCash').title(),
                    'status': st_norm,
                })
            ctx['recent_transactions'] = recent

            # ============================================================
            # USERS TAB KPIs & CHARTS
            # ============================================================
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
                rep, tot_s = int(row[0] or 0), int(row[1] or 0)
                ctx['usr_repeat_rate'] = f"{(rep / tot_s * 100):.1f}%" if tot_s else '0.0%'

            cursor.execute("""
                SELECT COUNT(*) FROM provider_verifications
                WHERE COALESCE(verification_status, 'Pending') = 'Pending'
            """)
            ctx['usr_pending_verifications'] = str(int(cursor.fetchone()[0] or 0))

            # Signups per month — Senders vs Providers using YYYY-MM string match
            cursor.execute("""
                SELECT
                    TO_CHAR(DATE_TRUNC('month', u.created_at), 'YYYY-MM') AS ym,
                    COUNT(DISTINCT u.user_id) FILTER (
                        WHERE LOWER(COALESCE(r.role_name, '')) = 'sender'
                           OR (r.role_name IS NULL AND pv.provider_id IS NULL)
                    ) AS senders,
                    COUNT(DISTINCT u.user_id) FILTER (
                        WHERE LOWER(COALESCE(r.role_name, '')) = 'provider'
                           OR pv.provider_id IS NOT NULL
                    ) AS providers
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN roles r ON r.role_id = ur.role_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                WHERE u.email != %s
                  AND u.created_at >= DATE_TRUNC('month', CURRENT_TIMESTAMP) - INTERVAL '5 months'
                GROUP BY ym
                ORDER BY ym
            """, [ADMIN_EMAIL])
            signups_by_ym = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in cursor.fetchall()}
            ctx['signup_senders']   = json.dumps([signups_by_ym.get(k, (0, 0))[0] for k in month_keys])
            ctx['signup_providers'] = json.dumps([signups_by_ym.get(k, (0, 0))[1] for k in month_keys])

            # Top providers
            cursor.execute("""
                SELECT
                    u.user_id,
                    COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '') AS name,
                    COUNT(DISTINCT d.delivery_id) FILTER (
                        WHERE LOWER(dr.delivery_status) IN ('completed', 'delivered')
                           OR d.completed_at IS NOT NULL
                    ) AS completed_cnt,
                    COALESCE(AVG(rr.rating), 0) AS avg_rating,
                    COALESCE(SUM(COALESCE(ep.amount, dr.estimated_cost, 0)) FILTER (
                        WHERE LOWER(COALESCE(ep.escrow_status, '')) IN ('released', 'completed')
                           OR d.completed_at IS NOT NULL
                    ), 0) AS earnings
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
            # BLOCKCHAIN AUDIT TAB
            # ============================================================
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

            query = """
                SELECT * FROM (
                    SELECT 'deliveries' AS category, 'Delivery Log' AS badge, 'DEL-' || bl.delivery_id::text AS ref_id, 
                           COALESCE(u.first_name || ' ' || u.last_name, 'Delivery #' || bl.delivery_id) AS entity_name,
                           'Blockchain Log #' || bl.id || ' · Delivery #' || bl.delivery_id AS details,
                           bl.tx_hash, COALESCE(bl.status, 'Confirmed') AS status, bl.created_at AS recorded_at
                    FROM blockchain_logs bl
                    LEFT JOIN deliveries d ON d.delivery_id = bl.delivery_id
                    LEFT JOIN users u ON u.user_id = d.provider_id

                    UNION ALL

                    SELECT 'verifications' AS category, 'Provider KYC' AS badge, 'US' || pv.provider_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Provider US' || pv.provider_id) AS entity_name,
                           'License: ' || pv.drivers_license_number || ' (' || pv.verification_status || ')' AS details,
                           pv.bc_verif_tx_hash AS tx_hash, 'Confirmed' AS status, COALESCE(pv.verified_at, pv.submitted_at) AS recorded_at
                    FROM provider_verifications pv
                    JOIN users u ON u.user_id = pv.provider_id
                    WHERE pv.bc_verif_tx_hash IS NOT NULL AND pv.bc_verif_tx_hash <> ''

                    UNION ALL

                    SELECT 'escrow' AS category, 'Escrow Payment' AS badge, 'ESC-' || ep.escrow_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Escrow #' || ep.escrow_id) AS entity_name,
                           '₱' || ep.amount || ' · ' || ep.escrow_status || ' (Delivery #' || ep.delivery_id || ')' AS details,
                           ep.bc_escrow_tx_hash AS tx_hash, 'Confirmed' AS status, ep.created_at AS recorded_at
                    FROM escrow_payments ep
                    LEFT JOIN users u ON u.user_id = ep.sender_id
                    WHERE ep.bc_escrow_tx_hash IS NOT NULL AND ep.bc_escrow_tx_hash <> ''

                    UNION ALL

                    SELECT 'qr' AS category, 'QR Pickup' AS badge, 'QR-' || qr.qr_id::text || '-P' AS ref_id,
                           'Delivery #' || qr.delivery_id || ' Pickup' AS entity_name,
                           'QR Handoff #' || qr.qr_id || ' · Pickup Verified' AS details,
                           qr.bc_pickup_tx_hash AS tx_hash, 'Confirmed' AS status, d.accepted_at AS recorded_at
                    FROM qr_verifications qr
                    JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE qr.bc_pickup_tx_hash IS NOT NULL AND qr.bc_pickup_tx_hash <> ''

                    UNION ALL

                    SELECT 'qr' AS category, 'QR Dropoff' AS badge, 'QR-' || qr.qr_id::text || '-D' AS ref_id,
                           'Delivery #' || qr.delivery_id || ' Dropoff' AS entity_name,
                           'QR Handoff #' || qr.qr_id || ' · Dropoff Verified' AS details,
                           qr.bc_dropoff_tx_hash AS tx_hash, 'Confirmed' AS status, d.completed_at AS recorded_at
                    FROM qr_verifications qr
                    JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE qr.bc_dropoff_tx_hash IS NOT NULL AND qr.bc_dropoff_tx_hash <> ''

                    UNION ALL

                    SELECT 'reviews' AS category, 'Rating & Review' AS badge, 'REV-' || rr.review_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Review #' || rr.review_id) AS entity_name,
                           '★ ' || rr.rating || '/5 · Delivery #' || rr.delivery_id AS details,
                           rr.bc_rating_tx_hash AS tx_hash, 'Confirmed' AS status, rr.created_at AS recorded_at
                    FROM ratings_reviews rr
                    LEFT JOIN users u ON u.user_id = rr.reviewee_id
                    WHERE rr.bc_rating_tx_hash IS NOT NULL AND rr.bc_rating_tx_hash <> ''

                    UNION ALL

                    SELECT 'transactions' AS category, 'Financial Tx' AS badge, 'TXN-' || t.transaction_id::text AS ref_id,
                           COALESCE(u.first_name || ' ' || u.last_name, 'Transaction #' || t.transaction_id) AS entity_name,
                           '₱' || t.total_amount || ' via ' || t.payment_method || ' (' || t.status || ') · Escrow #' || t.escrow_id AS details,
                           t.bc_tx_hash AS tx_hash, 'Confirmed' AS status, COALESCE(t.processed_at, CURRENT_TIMESTAMP) AS recorded_at
                    FROM transactions t
                    JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
                    LEFT JOIN users u ON u.user_id = ep.sender_id
                    WHERE t.bc_tx_hash IS NOT NULL AND t.bc_tx_hash <> ''

                    UNION ALL

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

            if proof_type and proof_type != 'all':
                query += " AND category = %s"
                params.append(proof_type)

            query += " ORDER BY recorded_at DESC NULLS LAST LIMIT 50"
            cursor.execute(query, params)

            records = []
            for r in cursor.fetchall():
                cat, badge, ref_id, entity_name, details, txh, status, rec_at = r
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
        import traceback
        traceback.print_exc()
        print(f"[reports] DB error: {e}")

    return render(request, 'pages/reports.html', ctx)