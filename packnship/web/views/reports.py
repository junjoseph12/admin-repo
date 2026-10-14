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