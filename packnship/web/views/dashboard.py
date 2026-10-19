# views/dashboard.py
from django.shortcuts import render
from django.db import connection
import json
from .login import admin_required


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