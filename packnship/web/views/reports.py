# views/reports.py
"""
Reports page (Overview / Deliveries / Financial / Users / Blockchain) + printable PDF export.

Everything here is read-only and written against the Supabase schema:
  delivery_requests, deliveries, escrow_payments, transactions, disputes, support_tickets,
  users, user_roles, roles, provider_verifications, ratings_reviews, qr_verifications,
  blockchain_logs, withdrawal_requests, provider_wallet.

Two outputs share ONE context builder:
  /reports/?tab=...            -> pages/reports.html        (screen)
  /reports/?tab=...&export=1   -> pages/reports_print.html  (company-style report, Save as PDF)
"""
import json
import traceback
from datetime import datetime, timedelta

from django.db import connection
from django.shortcuts import render

from .login import admin_required

ADMIN_EMAIL = 'admin@packnship.com'
# Used ONLY for payments that have no row in `transactions`. Real service_fee/penalty_fee always win.
PLATFORM_FEE_RATE = 0.10

PERIOD_LABELS = {
    'this_month': 'This Month',
    'last_month': 'Last Month',
    'last_3_months': 'Last 3 Months',
    'this_year': 'This Year',
}
TAB_LABELS = {
    'overview': 'Executive Overview',
    'deliveries': 'Delivery Operations',
    'financial': 'Financial Performance',
    'users': 'User & Provider Activity',
    'blockchain': 'Blockchain Audit Trail',
}

ICONS = {
    'check':   'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    'money':   'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    'trend':   'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
    'x':       'M6 18L18 6M6 6l12 12',
    'warning': 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
    'users':   'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
}

# ----------------------------------------------------------------------------------------------
# SQL building blocks
# ----------------------------------------------------------------------------------------------
# One row per delivery REQUEST (latest delivery attached), with a status bucket and a "disputed" flag.
BUCKET_SQL = """
CASE
  WHEN LOWER(COALESCE(dr.delivery_status, '')) IN ('cancelled', 'canceled') THEN 'cancelled'
  WHEN LOWER(COALESCE(dr.delivery_status, '')) IN ('completed', 'delivered') OR d.completed_at IS NOT NULL THEN 'completed'
  WHEN d.failed_at IS NOT NULL OR d.returned_at IS NOT NULL
       OR POSITION('fail' IN LOWER(COALESCE(dr.delivery_status, ''))) > 0 THEN 'failed'
  WHEN d.delivery_id IS NOT NULL THEN 'in_transit'
  ELSE 'pending'
END
"""

LATEST_DELIVERY = """
LEFT JOIN LATERAL (
    SELECT x.* FROM deliveries x
    WHERE x.request_id = dr.request_id
    ORDER BY x.delivery_id DESC
    LIMIT 1
) d ON TRUE
"""

REQ_CTE = f"""
WITH req AS (
    SELECT dr.request_id, dr.created_at, dr.sender_id,
           LOWER(COALESCE(dr.pickup_type, '')) AS ptype,
           d.delivery_id AS d_id, d.provider_id, d.accepted_at, d.completed_at,
           {BUCKET_SQL} AS bucket,
           (d.delivery_id IS NOT NULL AND (
               EXISTS (SELECT 1 FROM disputes ds WHERE ds.delivery_id = d.delivery_id)
               OR EXISTS (SELECT 1 FROM support_tickets st
                          WHERE st.type = 'dispute'
                            AND (st.delivery_id = d.delivery_id OR st.request_id = dr.request_id))
           )) AS disputed
    FROM delivery_requests dr
    {LATEST_DELIVERY}
)
"""

# One row per PAID request. gmv/net come from `transactions` when present (real service fee + penalty),
# otherwise gmv falls back to the request's estimated_cost and net stays 0 (no invented fee).
FIN_CTE = f"""
WITH fin AS (
    SELECT dr.request_id, d.delivery_id AS d_id,
           COALESCE(t.processed_at, dr.paid_at, ep.created_at, d.completed_at, dr.created_at) AS fin_at,
           COALESCE(dr.escrow_refunded_at, ep.created_at, dr.paid_at) AS ref_at,
           COALESCE(t.total_amount, ep.amount, dr.estimated_cost, 0) AS gmv,
           CASE WHEN t.transaction_id IS NOT NULL
                THEN COALESCE(t.service_fee, 0) + COALESCE(t.penalty_fee, 0)
                ELSE COALESCE(ep.amount, dr.estimated_cost, 0) * {PLATFORM_FEE_RATE}
           END AS net,
           CASE WHEN LOWER(COALESCE(t.payment_method, dr.payment_provider, '')) = 'paymaya' THEN 'maya'
                ELSE LOWER(COALESCE(t.payment_method, dr.payment_provider, '')) END AS pm,
           (dr.escrow_refunded_at IS NOT NULL
            OR LOWER(COALESCE(ep.escrow_status, '')) = 'refunded') AS refunded,
           (LOWER(COALESCE(dr.delivery_status, '')) IN ('cancelled', 'canceled')) AS cancelled
    FROM delivery_requests dr
    {LATEST_DELIVERY}
    LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
    LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
    WHERE dr.paid_at IS NOT NULL
       OR t.transaction_id IS NOT NULL
       OR ep.escrow_id IS NOT NULL
       OR d.completed_at IS NOT NULL
       OR LOWER(COALESCE(dr.delivery_status, '')) IN ('completed', 'delivered')
)
"""

_ROLE = ("EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.role_id = ur.role_id "
         "WHERE ur.user_id = u.user_id AND LOWER(r.role_name) = '{role}')")
IS_PROVIDER = _ROLE.format(role='provider')
IS_ADMIN = _ROLE.format(role='admin')
IS_SENDER = f"({_ROLE.format(role='sender')} OR (NOT {IS_PROVIDER} AND NOT {IS_ADMIN}))"

BC_UNION = """
SELECT 'deliveries' AS category, 'Delivery Log' AS badge, 'DEL-' || bl.delivery_id::text AS ref_id,
       COALESCE(u.first_name || ' ' || u.last_name, 'Delivery #' || bl.delivery_id) AS entity_name,
       'Blockchain Log #' || bl.id || ' · Delivery #' || bl.delivery_id AS details,
       bl.tx_hash AS tx_hash, COALESCE(bl.status, 'Confirmed') AS status, bl.created_at AS recorded_at
FROM blockchain_logs bl
LEFT JOIN deliveries d ON d.delivery_id = bl.delivery_id
LEFT JOIN users u ON u.user_id = d.provider_id

UNION ALL
SELECT 'verifications', 'Provider KYC', 'US' || pv.provider_id::text,
       COALESCE(u.first_name || ' ' || u.last_name, 'Provider US' || pv.provider_id),
       'License: ' || pv.drivers_license_number || ' (' || pv.verification_status || ')',
       pv.bc_verif_tx_hash, 'Confirmed', COALESCE(pv.verified_at, pv.submitted_at)
FROM provider_verifications pv
JOIN users u ON u.user_id = pv.provider_id
WHERE pv.bc_verif_tx_hash IS NOT NULL AND pv.bc_verif_tx_hash <> ''

UNION ALL
SELECT 'escrow', 'Escrow Payment', 'ESC-' || ep.escrow_id::text,
       COALESCE(u.first_name || ' ' || u.last_name, 'Escrow #' || ep.escrow_id),
       '₱' || ep.amount || ' · ' || ep.escrow_status || ' (Delivery #' || ep.delivery_id || ')',
       ep.bc_escrow_tx_hash, 'Confirmed', ep.created_at
FROM escrow_payments ep
LEFT JOIN users u ON u.user_id = ep.sender_id
WHERE ep.bc_escrow_tx_hash IS NOT NULL AND ep.bc_escrow_tx_hash <> ''

UNION ALL
SELECT 'qr', 'QR Pickup', 'QR-' || qr.qr_id::text || '-P',
       'Delivery #' || qr.delivery_id || ' Pickup',
       'QR Handoff #' || qr.qr_id || ' · Pickup Verified',
       qr.bc_pickup_tx_hash, 'Confirmed', COALESCE(d.pickup_photo_taken_at, d.accepted_at)
FROM qr_verifications qr
JOIN deliveries d ON d.delivery_id = qr.delivery_id
WHERE qr.bc_pickup_tx_hash IS NOT NULL AND qr.bc_pickup_tx_hash <> ''

UNION ALL
SELECT 'qr', 'QR Dropoff', 'QR-' || qr.qr_id::text || '-D',
       'Delivery #' || qr.delivery_id || ' Dropoff',
       'QR Handoff #' || qr.qr_id || ' · Dropoff Verified',
       qr.bc_dropoff_tx_hash, 'Confirmed', COALESCE(d.completed_at, d.accepted_at)
FROM qr_verifications qr
JOIN deliveries d ON d.delivery_id = qr.delivery_id
WHERE qr.bc_dropoff_tx_hash IS NOT NULL AND qr.bc_dropoff_tx_hash <> ''

UNION ALL
SELECT 'reviews', 'Rating & Review', 'REV-' || rr.review_id::text,
       COALESCE(u.first_name || ' ' || u.last_name, 'Review #' || rr.review_id),
       '★ ' || rr.rating || '/5 · Delivery #' || rr.delivery_id,
       rr.bc_rating_tx_hash, 'Confirmed', rr.created_at
FROM ratings_reviews rr
LEFT JOIN users u ON u.user_id = rr.reviewee_id
WHERE rr.bc_rating_tx_hash IS NOT NULL AND rr.bc_rating_tx_hash <> ''

UNION ALL
SELECT 'transactions', 'Financial Tx', 'TXN-' || t.transaction_id::text,
       COALESCE(u.first_name || ' ' || u.last_name, 'Transaction #' || t.transaction_id),
       '₱' || t.total_amount || ' via ' || t.payment_method || ' (' || t.status || ') · Escrow #' || t.escrow_id,
       t.bc_tx_hash, 'Confirmed', COALESCE(t.processed_at, ep.created_at)
FROM transactions t
JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
LEFT JOIN users u ON u.user_id = ep.sender_id
WHERE t.bc_tx_hash IS NOT NULL AND t.bc_tx_hash <> ''

UNION ALL
SELECT 'withdrawals', 'Withdrawal', 'WDR-' || w.withdrawal_id::text,
       COALESCE(u.first_name || ' ' || u.last_name, 'Withdrawal #' || w.withdrawal_id),
       '₱' || w.amount || ' via ' || w.method || ' (' || w.status || ')',
       w.bc_tx_hash, 'Confirmed', COALESCE(w.processed_at, w.requested_at)
FROM withdrawal_requests w
JOIN provider_wallet pw ON pw.wallet_id = w.provider_wallet_id
LEFT JOIN users u ON u.user_id = pw.provider_id
WHERE w.bc_tx_hash IS NOT NULL AND w.bc_tx_hash <> ''
"""

BADGE_COLORS = {
    'Provider KYC': 'green', 'Escrow Payment': 'blue', 'QR Pickup': 'purple', 'QR Dropoff': 'purple',
    'Rating & Review': 'amber', 'Financial Tx': 'blue', 'Withdrawal': 'purple',
}


# ----------------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------------
def _add_months(dt, n):
    y = dt.year + (dt.month - 1 + n) // 12
    m = (dt.month - 1 + n) % 12 + 1
    return dt.replace(year=y, month=m, day=1)


def _period_bounds(key):
    """Returns (start, end, prev_start, prev_end, label). `end` is exclusive."""
    now = datetime.now()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if key == 'last_month':
        start, end = _add_months(first, -1), first
    elif key == 'last_3_months':
        start, end = _add_months(first, -2), now
    elif key == 'this_year':
        start, end = first.replace(month=1), now
    else:
        start, end = first, now
    prev_end = start
    prev_start = start - (end - start)
    last_day = end - timedelta(seconds=1)
    label = f"{start.strftime('%b %d, %Y')} – {last_day.strftime('%b %d, %Y')}"
    return start, end, prev_start, prev_end, label


def _peso(v, dec=0):
    return f"₱{float(v or 0):,.{dec}f}"


def _rate(num, den):
    return (num / den * 100.0) if den else 0.0


def _pct_txt(v):
    return f"{v:.1f}%"


def _minutes_txt(mins):
    if mins is None:
        return '—'
    m = max(0.0, float(mins))
    if m < 60:
        return f"{m:.0f}m"
    if m < 1440:
        return f"{m / 60:.1f}h"
    return f"{m / 1440:.1f}d"


def _delta_pct(cur, prev, higher_better=True):
    """Relative change for counts / money."""
    cur, prev = float(cur or 0), float(prev or 0)
    if prev == 0 and cur == 0:
        return {'text': '0.0%', 'tone': 'neutral', 'arrow': '→'}
    if prev == 0:
        return {'text': 'New', 'tone': 'good' if higher_better else 'bad', 'arrow': '↗'}
    ch = (cur - prev) / prev * 100.0
    if abs(ch) < 0.05:
        return {'text': '0.0%', 'tone': 'neutral', 'arrow': '→'}
    good = (ch > 0) == higher_better
    return {'text': f"{abs(ch):.1f}%", 'tone': 'good' if good else 'bad', 'arrow': '↗' if ch > 0 else '↘'}


def _delta_pts(cur_rate, prev_rate, has_prev, higher_better=True):
    """Difference in percentage points for rates."""
    if not has_prev:
        return {'text': 'n/a', 'tone': 'neutral', 'arrow': '→'}
    d = cur_rate - prev_rate
    if abs(d) < 0.05:
        return {'text': '0.0 pts', 'tone': 'neutral', 'arrow': '→'}
    good = (d > 0) == higher_better
    return {'text': f"{abs(d):.1f} pts", 'tone': 'good' if good else 'bad', 'arrow': '↗' if d > 0 else '↘'}


def _kpi(label, value, hint='', accent='#9ca3af', accent2='#e5e7eb', color='var(--text-primary)',
         icon=None, icon_bg='var(--bg-surface-muted)', icon_fg='var(--text-muted)', delta=None):
    return {
        'label': label, 'value': value, 'hint': hint, 'accent': accent, 'accent2': accent2, 'color': color,
        'icon_path': ICONS.get(icon, ''), 'icon_bg': icon_bg, 'icon_fg': icon_fg, 'delta': delta,
    }


def _delivery_filter(dtype, status, params):
    """Extra WHERE for the `req` CTE (Deliveries tab filters)."""
    sql = ''
    curb = "(POSITION('curb' IN ptype) > 0 OR POSITION('station' IN ptype) > 0 OR POSITION('meetup' IN ptype) > 0)"
    if dtype == 'curbside':
        sql += f" AND {curb}"
    elif dtype == 'door':
        sql += (f" AND NOT {curb} AND (POSITION('door' IN ptype) > 0 OR POSITION('home' IN ptype) > 0"
                f" OR POSITION('direct' IN ptype) > 0)")
    if status in ('completed', 'cancelled', 'in_transit', 'pending', 'failed'):
        sql += " AND bucket = %(status)s"
        params['status'] = status
    return sql


def _pm_filter(method, params):
    if method == 'gcash':
        params['pms'] = ['gcash']
        return " AND pm = ANY(%(pms)s)"
    if method == 'maya':
        params['pms'] = ['maya']
        return " AND pm = ANY(%(pms)s)"
    return ''


# ----------------------------------------------------------------------------------------------
# reusable queries
# ----------------------------------------------------------------------------------------------
def _delivery_stats(cur, start, end, extra='', extra_params=None):
    params = {'start': start, 'end': end}
    params.update(extra_params or {})
    cur.execute(REQ_CTE + f"""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE bucket = 'completed'),
               COUNT(*) FILTER (WHERE bucket = 'cancelled'),
               COUNT(*) FILTER (WHERE bucket = 'failed'),
               COUNT(*) FILTER (WHERE d_id IS NOT NULL),
               COUNT(*) FILTER (WHERE disputed),
               COUNT(*) FILTER (WHERE d_id IS NOT NULL AND (bucket = 'failed' OR disputed)),
               AVG(EXTRACT(EPOCH FROM (completed_at - accepted_at)) / 60.0)
                   FILTER (WHERE completed_at IS NOT NULL AND accepted_at IS NOT NULL)
        FROM req
        WHERE created_at >= %(start)s AND created_at < %(end)s {extra}
    """, params)
    r = cur.fetchone()
    return {
        'total': int(r[0] or 0), 'completed': int(r[1] or 0), 'cancelled': int(r[2] or 0),
        'failed': int(r[3] or 0), 'accepted': int(r[4] or 0), 'disputed': int(r[5] or 0),
        'exceptions': int(r[6] or 0), 'avg_mins': float(r[7]) if r[7] is not None else None,
    }


def _money(cur, start, end, method=''):
    """(gmv, net, refunded) for the window. GMV and net exclude refunded payments."""
    params = {'start': start, 'end': end}
    pm = _pm_filter(method, params)
    cur.execute(FIN_CTE + f"""
        SELECT COALESCE(SUM(gmv) FILTER (WHERE NOT refunded AND NOT cancelled), 0),
               COALESCE(SUM(net) FILTER (WHERE NOT refunded AND NOT cancelled), 0)
        FROM fin WHERE fin_at >= %(start)s AND fin_at < %(end)s {pm}
    """, params)
    gmv, net = cur.fetchone()
    cur.execute(FIN_CTE + f"""
        SELECT COALESCE(SUM(gmv), 0) FROM fin
        WHERE refunded AND ref_at >= %(start)s AND ref_at < %(end)s {pm}
    """, params)
    refunded = cur.fetchone()[0]
    return float(gmv or 0), float(net or 0), float(refunded or 0)


def _active_users(cur, start, end):
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT sender_id AS uid FROM delivery_requests WHERE created_at >= %(s)s AND created_at < %(e)s
            UNION
            SELECT provider_id FROM deliveries WHERE accepted_at >= %(s)s AND accepted_at < %(e)s
        ) a
    """, {'s': start, 'e': end})
    return int(cur.fetchone()[0] or 0)


def _new_users(cur, start, end, role=''):
    role_sql = ''
    if role == 'provider':
        role_sql = f" AND {IS_PROVIDER}"
    elif role == 'sender':
        role_sql = f" AND {IS_SENDER}"
    cur.execute(f"""
        SELECT COUNT(*) FROM users u
        WHERE u.created_at >= %(s)s AND u.created_at < %(e)s
          AND u.email <> %(admin)s AND NOT {IS_ADMIN} {role_sql}
    """, {'s': start, 'e': end, 'admin': ADMIN_EMAIL})
    return int(cur.fetchone()[0] or 0)


# ----------------------------------------------------------------------------------------------
# view
# ----------------------------------------------------------------------------------------------
@admin_required
def reports(request):
    tab = request.GET.get('tab', 'overview')
    if tab not in TAB_LABELS:
        tab = 'overview'
    period = request.GET.get('period', 'this_month')
    if period not in PERIOD_LABELS:
        period = 'this_month'
    dtype = request.GET.get('delivery_type', '')
    status_filter = request.GET.get('status', '')
    pay_method = request.GET.get('payment_method', '')
    role_filter = request.GET.get('role', '')
    proof_type = request.GET.get('proof_type', '') or 'all'
    export = request.GET.get('export') == '1'

    start, end, prev_start, prev_end, period_range = _period_bounds(period)
    now = datetime.now()

    # 6 month trend window (current month + 5 previous)
    m_first = _add_months(now.replace(hour=0, minute=0, second=0, microsecond=0), -5)
    month_dates = [_add_months(m_first, i) for i in range(6)]
    month_keys = [d.strftime('%Y-%m') for d in month_dates]
    month_labels = [d.strftime("%b '%y") for d in month_dates]

    export_params = request.GET.copy()
    export_params['export'] = '1'

    # human readable "filters applied" for the export header
    applied = []
    if tab == 'deliveries':
        if dtype:
            applied.append(('Delivery type', 'Curb-side' if dtype == 'curbside' else 'Door-to-Door'))
        if status_filter:
            applied.append(('Status', status_filter.replace('_', ' ').title()))
    elif tab == 'financial':
        if pay_method:
            applied.append(('Payment method', pay_method.upper() if pay_method == 'gcash' else pay_method.title()))
        if status_filter:
            applied.append(('Status', status_filter.replace('_', ' ').title()))
    elif tab == 'users' and role_filter:
        applied.append(('Role', role_filter.title()))
    elif tab == 'blockchain' and proof_type != 'all':
        applied.append(('Proof type', proof_type.title()))

    session = request.session
    ctx = {
        'current_tab': tab,
        'tab_title': TAB_LABELS[tab],
        'selected_period': period,
        'period_label': PERIOD_LABELS[period],
        'period_range': period_range,
        'status_filter': status_filter,
        'delivery_type_filter': dtype,
        'payment_method_filter': pay_method,
        'role_filter': role_filter,
        'proof_type_filter': proof_type,
        'export_query': export_params.urlencode(),
        'applied_filters': applied,
        'generated_at': now.strftime('%B %d, %Y · %I:%M %p'),
        'generated_by': session.get('admin_name') or session.get('admin_email') or 'Administrator',
        'report_ref': 'PNS-RPT-' + now.strftime('%Y%m%d-%H%M'),
        'ov_kpis': [], 'del_kpis': [], 'fin_kpis': [], 'usr_kpis': [], 'bc_kpis': [],
        'weekly_rows': [], 'type_rows': [], 'month_rows': [], 'payment_rows': [],
        'top_providers': [], 'recent_transactions': [], 'blockchain_records': [], 'bc_modules': [],
        'chart_data': {},
        'db_error': '',
    }

    chart = {
        'months': month_labels,
        'overview': {'deliveries': [0] * 6, 'net': [0] * 6},
        'status': {'labels': [], 'completed': [], 'in_transit': [], 'pending': [], 'cancelled': [], 'failed': []},
        'dtype': {'labels': ['Curb-side', 'Door-to-Door'], 'values': [0, 0]},
        'revenue': {'gmv': [0] * 6, 'net': [0] * 6},
        'payment': {'labels': ['GCash', 'Maya'], 'values': [0, 0]},
        'signups': {'senders': [0] * 6, 'providers': [0] * 6,
                    'show_senders': role_filter != 'provider', 'show_providers': role_filter != 'sender'},
    }
    ctx['chart_data'] = chart

    try:
        with connection.cursor() as cur:
            # ======================================================================
            # 6-month trend (used by Overview / Financial / Users)
            # ======================================================================
            cur.execute(REQ_CTE + """
                SELECT TO_CHAR(DATE_TRUNC('month', COALESCE(completed_at, created_at)), 'YYYY-MM'), COUNT(*)
                FROM req
                WHERE bucket = 'completed' AND COALESCE(completed_at, created_at) >= %(m0)s
                GROUP BY 1
            """, {'m0': m_first})
            del_m = {r[0]: int(r[1]) for r in cur.fetchall()}

            fin_m = {}
            if tab in ('overview', 'financial'):
                params = {'m0': m_first}
                pm = _pm_filter(pay_method if tab == 'financial' else '', params)
                cur.execute(FIN_CTE + f"""
                    SELECT TO_CHAR(DATE_TRUNC('month', fin_at), 'YYYY-MM'),
                           COALESCE(SUM(gmv), 0), COALESCE(SUM(net), 0)
                    FROM fin WHERE NOT refunded AND NOT cancelled AND fin_at >= %(m0)s {pm}
                    GROUP BY 1
                """, params)
                fin_m = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in cur.fetchall()}

            sign_m = {}
            if tab in ('overview', 'users'):
                cur.execute(f"""
                    SELECT TO_CHAR(DATE_TRUNC('month', u.created_at), 'YYYY-MM'),
                           COUNT(*) FILTER (WHERE {IS_SENDER}),
                           COUNT(*) FILTER (WHERE {IS_PROVIDER})
                    FROM users u
                    WHERE u.email <> %(admin)s AND NOT {IS_ADMIN} AND u.created_at >= %(m0)s
                    GROUP BY 1
                """, {'m0': m_first, 'admin': ADMIN_EMAIL})
                sign_m = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in cur.fetchall()}

            chart['overview']['deliveries'] = [del_m.get(k, 0) for k in month_keys]
            chart['overview']['net'] = [round(fin_m.get(k, (0, 0))[1], 2) for k in month_keys]
            chart['revenue']['gmv'] = [round(fin_m.get(k, (0, 0))[0], 2) for k in month_keys]
            chart['revenue']['net'] = [round(fin_m.get(k, (0, 0))[1], 2) for k in month_keys]
            chart['signups']['senders'] = [sign_m.get(k, (0, 0))[0] for k in month_keys]
            chart['signups']['providers'] = [sign_m.get(k, (0, 0))[1] for k in month_keys]

            for i, k in enumerate(month_keys):
                ctx['month_rows'].append({
                    'label': month_labels[i],
                    'deliveries': del_m.get(k, 0),
                    'gmv': _peso(fin_m.get(k, (0, 0))[0]),
                    'net': _peso(fin_m.get(k, (0, 0))[1]),
                    'senders': sign_m.get(k, (0, 0))[0],
                    'providers': sign_m.get(k, (0, 0))[1],
                })

            # ======================================================================
            # OVERVIEW
            # ======================================================================
            if tab == 'overview':
                cur_s = _delivery_stats(cur, start, end)
                prv_s = _delivery_stats(cur, prev_start, prev_end)
                has_prev = prv_s['total'] > 0

                gmv, net, _ref = _money(cur, start, end)
                p_gmv, p_net, _pr = _money(cur, prev_start, prev_end)

                act, p_act = _active_users(cur, start, end), _active_users(cur, prev_start, prev_end)
                new_u = _new_users(cur, start, end)

                fulfil = _rate(cur_s['completed'], cur_s['total'])
                p_fulfil = _rate(prv_s['completed'], prv_s['total'])
                cancel = _rate(cur_s['cancelled'], cur_s['total'])
                p_cancel = _rate(prv_s['cancelled'], prv_s['total'])
                disp = _rate(cur_s['disputed'], cur_s['accepted'])
                p_disp = _rate(prv_s['disputed'], prv_s['accepted'])

                ctx['ov_kpis'] = [
                    _kpi('Completed Deliveries', str(cur_s['completed']), 'vs. previous period',
                         '#34d399', '#d1fae5', icon='check', icon_bg='var(--status-success-bg)',
                         icon_fg='var(--status-success)', delta=_delta_pct(cur_s['completed'], prv_s['completed'])),
                    _kpi('Net Revenue', _peso(net), 'Service fees (10% est. if no transaction row), vs. previous period',
                         '#FF751F', '#ffedd5', color='var(--brand)', icon='money', icon_bg='var(--brand-soft)',
                         icon_fg='var(--brand-ink)', delta=_delta_pct(net, p_net)),
                    _kpi('Fulfillment Rate', _pct_txt(fulfil), 'Completed ÷ total requests',
                         '#60a5fa', '#dbeafe', icon='trend', icon_bg='var(--status-info-bg)',
                         icon_fg='var(--status-info)', delta=_delta_pts(fulfil, p_fulfil, has_prev)),
                    _kpi('Cancellation Rate', _pct_txt(cancel), 'Cancelled ÷ total requests · lower is better',
                         '#9ca3af', '#e5e7eb', icon='x', delta=_delta_pts(cancel, p_cancel, has_prev, False)),
                    _kpi('Dispute Rate', _pct_txt(disp), 'Disputed ÷ accepted deliveries · lower is better',
                         '#f87171', '#ffe4e6', icon='warning', icon_bg='var(--status-danger-bg)',
                         icon_fg='var(--status-danger)',
                         delta=_delta_pts(disp, p_disp, prv_s['accepted'] > 0, False)),
                    _kpi('Active Users', str(act), f'{new_u} new signups · senders + providers',
                         '#c084fc', '#f3e8ff', icon='users', icon_bg='rgba(168,85,247,0.1)', icon_fg='#c084fc',
                         delta=_delta_pct(act, p_act)),
                ]
                ctx['ov_totals'] = {'requests': cur_s['total'], 'gmv': _peso(gmv)}

            # ======================================================================
            # DELIVERIES
            # ======================================================================
            if tab == 'deliveries':
                params = {}
                extra = _delivery_filter(dtype, status_filter, params)
                s = _delivery_stats(cur, start, end, extra, params)
                ctx['del_kpis'] = [
                    _kpi('Total Requests', str(s['total']), accent='#9ca3af', accent2='#e5e7eb'),
                    _kpi('Completion Rate', _pct_txt(_rate(s['completed'], s['total'])), 'Completed ÷ requests',
                         '#34d399', '#d1fae5', color='var(--status-success)'),
                    _kpi('Cancellation Rate', _pct_txt(_rate(s['cancelled'], s['total'])), 'Cancelled ÷ requests'),
                    _kpi('Avg. Fulfillment', _minutes_txt(s['avg_mins']), 'Accepted → completed',
                         '#60a5fa', '#dbeafe'),
                    _kpi('Exception Rate', _pct_txt(_rate(s['exceptions'], s['accepted'])),
                         'Failed or disputed ÷ accepted', '#f87171', '#ffe4e6', color='var(--status-danger)'),
                ]

                # weekly rows (last 6 weeks, same filters)
                wparams = {}
                wextra = _delivery_filter(dtype, status_filter, wparams)
                cur.execute(REQ_CTE + f"""
                    , weeks AS (
                        SELECT (DATE_TRUNC('week', CURRENT_TIMESTAMP) - (n || ' week')::interval)::timestamp AS w
                        FROM generate_series(5, 0, -1) AS n
                    ), f AS (SELECT * FROM req WHERE TRUE {wextra})
                    SELECT TO_CHAR(w.w, 'Mon DD'),
                           COUNT(f.request_id),
                           COUNT(f.request_id) FILTER (WHERE f.bucket = 'completed'),
                           COUNT(f.request_id) FILTER (WHERE f.bucket = 'in_transit'),
                           COUNT(f.request_id) FILTER (WHERE f.bucket = 'pending'),
                           COUNT(f.request_id) FILTER (WHERE f.bucket = 'cancelled'),
                           COUNT(f.request_id) FILTER (WHERE f.bucket = 'failed'),
                           AVG(EXTRACT(EPOCH FROM (f.completed_at - f.accepted_at)) / 60.0)
                               FILTER (WHERE f.completed_at IS NOT NULL AND f.accepted_at IS NOT NULL)
                    FROM weeks w
                    LEFT JOIN f ON f.created_at >= w.w AND f.created_at < w.w + INTERVAL '1 week'
                    GROUP BY w.w ORDER BY w.w
                """, wparams)
                st = chart['status']
                for lbl, req, comp, trn, pen, can, fai, avg_m in cur.fetchall():
                    st['labels'].append(lbl)
                    st['completed'].append(int(comp or 0))
                    st['in_transit'].append(int(trn or 0))
                    st['pending'].append(int(pen or 0))
                    st['cancelled'].append(int(can or 0))
                    st['failed'].append(int(fai or 0))
                    ctx['weekly_rows'].append({
                        'label': lbl, 'requests': int(req or 0), 'completed': int(comp or 0),
                        'in_transit': int(trn or 0), 'pending': int(pen or 0),
                        'cancelled': int(can or 0), 'failed': int(fai or 0),
                        'duration': _minutes_txt(avg_m),
                    })

                # delivery type split (period, same status filter, no type filter)
                tparams = {'start': start, 'end': end}
                text = ''
                if status_filter in ('completed', 'cancelled', 'in_transit', 'pending', 'failed'):
                    text = " AND bucket = %(status)s"
                    tparams['status'] = status_filter
                cur.execute(REQ_CTE + f"""
                    SELECT ptype, COUNT(*) FROM req
                    WHERE created_at >= %(start)s AND created_at < %(end)s {text}
                    GROUP BY ptype
                """, tparams)
                curb = door = 0
                others = {}
                for ptype, cnt in cur.fetchall():
                    cnt = int(cnt or 0)
                    if 'curb' in ptype or 'station' in ptype or 'meetup' in ptype:
                        curb += cnt
                    elif 'door' in ptype or 'home' in ptype or 'direct' in ptype:
                        door += cnt
                    elif ptype:
                        others[ptype.title()] = others.get(ptype.title(), 0) + cnt
                    else:
                        others['Unspecified'] = others.get('Unspecified', 0) + cnt
                labels, values = ['Curb-side', 'Door-to-Door'], [curb, door]
                if others:
                    labels.append('Other')
                    values.append(sum(others.values()))
                chart['dtype'] = {'labels': labels, 'values': values}
                tot_t = sum(values)
                ctx['type_rows'] = [
                    {'label': l, 'count': v, 'share': _pct_txt(_rate(v, tot_t))} for l, v in zip(labels, values)
                ]

            # ======================================================================
            # FINANCIAL
            # ======================================================================
            if tab == 'financial':
                gmv, net, refunded = _money(cur, start, end, pay_method)
                cur.execute("""
                    SELECT COALESCE(SUM(amount), 0) FROM escrow_payments
                    WHERE emergency_frozen OR LOWER(escrow_status) IN ('on hold', 'on_hold', 'pending', 'frozen')
                """)
                held = float(cur.fetchone()[0] or 0)
                ctx['fin_kpis'] = [
                    _kpi('GMV', _peso(gmv), 'Paid, excl. refunds', '#9ca3af', '#e5e7eb'),
                    _kpi('Net Revenue', _peso(net), 'Service fees (10% est. if no transaction row)', '#FF751F', '#ffedd5',
                         color='var(--brand)'),
                    _kpi('Take Rate', _pct_txt(_rate(net, gmv)), 'Net ÷ GMV', '#60a5fa', '#dbeafe'),
                    _kpi('Escrow On Hold', _peso(held), 'Current balance', '#fbbf24', '#fef3c7'),
                    _kpi('Refunded', _peso(refunded), 'In this period', '#f87171', '#ffe4e6'),
                ]

                params = {'start': start, 'end': end}
                pm = _pm_filter(pay_method, params)
                cur.execute(FIN_CTE + f"""
                    SELECT CASE WHEN pm = '' THEN 'other' ELSE pm END, COALESCE(SUM(gmv), 0), COUNT(*)
                    FROM fin
                    WHERE NOT refunded AND NOT cancelled AND fin_at >= %(start)s AND fin_at < %(end)s {pm}
                    GROUP BY 1
                """, params)
                pm_map = {r[0]: (float(r[1] or 0), int(r[2] or 0)) for r in cur.fetchall()}
                labels, values, p_total = [], [], sum(v[0] for v in pm_map.values())
                for key, name in (('gcash', 'GCash'), ('maya', 'Maya')):
                    amt, cnt = pm_map.pop(key, (0.0, 0))
                    labels.append(name)
                    values.append(round(amt, 2))
                    ctx['payment_rows'].append({'label': name, 'count': cnt, 'amount': _peso(amt),
                                                'share': _pct_txt(_rate(amt, p_total))})
                rest_amt = sum(v[0] for v in pm_map.values())
                rest_cnt = sum(v[1] for v in pm_map.values())
                if rest_amt:
                    labels.append('Other')
                    values.append(round(rest_amt, 2))
                    ctx['payment_rows'].append({'label': 'Other', 'count': rest_cnt, 'amount': _peso(rest_amt),
                                                'share': _pct_txt(_rate(rest_amt, p_total))})
                chart['payment'] = {'labels': labels, 'values': values}

                # transactions table
                tparams = {'start': start, 'end': end, 'limit': 40 if export else 10}
                tpm = ''
                if pay_method in ('gcash', 'maya'):
                    tparams['pms'] = [pay_method]
                    tpm = (" AND (CASE WHEN LOWER(COALESCE(t.payment_method, dr.payment_provider, '')) = 'paymaya' "
                           "THEN 'maya' ELSE LOWER(COALESCE(t.payment_method, dr.payment_provider, '')) END) = ANY(%(pms)s)")
                tsf = ''
                if status_filter in ('completed', 'on_hold', 'refunded'):
                    tsf = "AND LOWER(REPLACE(status, ' ', '_')) = %(sf)s"
                    tparams['sf'] = status_filter
                cur.execute(f"""
                    SELECT * FROM (
                        SELECT COALESCE('TXN-' || t.transaction_id::text, 'ESC-' || ep.escrow_id::text,
                                        'REQ-' || dr.request_id::text) AS ref,
                               d.delivery_id,
                               COALESCE(t.total_amount, ep.amount, dr.estimated_cost, 0) AS amount,
                               COALESCE(NULLIF(t.payment_method, ''), NULLIF(dr.payment_provider, ''), '—') AS method,
                               CASE
                                 WHEN dr.escrow_refunded_at IS NOT NULL
                                      OR LOWER(COALESCE(ep.escrow_status, '')) = 'refunded' THEN 'Refunded'
                                 WHEN LOWER(COALESCE(ep.escrow_status, '')) IN ('released', 'completed')
                                      OR LOWER(COALESCE(t.status, '')) IN ('completed', 'success', 'paid', 'released') THEN 'Completed'
                                 WHEN ep.emergency_frozen
                                      OR LOWER(COALESCE(ep.escrow_status, '')) IN ('on hold', 'on_hold', 'frozen') THEN 'On Hold'
                                 ELSE 'Pending'
                               END AS status,
                               COALESCE(t.processed_at, dr.paid_at, ep.created_at, dr.created_at) AS at
                        FROM delivery_requests dr
                        {LATEST_DELIVERY}
                        LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                        LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                        WHERE (dr.paid_at IS NOT NULL OR t.transaction_id IS NOT NULL) {tpm}
                    ) x
                    WHERE at >= %(start)s AND at < %(end)s
                    {tsf}
                    ORDER BY at DESC LIMIT %(limit)s
                """, tparams)
                for ref, did, amt, method, st_txt, at in cur.fetchall():
                    m = str(method)
                    ctx['recent_transactions'].append({
                        'id': ref, 'delivery_id': did or '—', 'amount': _peso(amt, 2),
                        'method': 'GCash' if m.lower() == 'gcash' else ('Maya' if m.lower() in ('maya', 'paymaya') else m.title()),
                        'status': st_txt, 'date': at.strftime('%b %d, %Y') if at else '—',
                    })

            # ======================================================================
            # USERS
            # ======================================================================
            if tab == 'users':
                new_u = _new_users(cur, start, end, role_filter)
                cur.execute(REQ_CTE + """
                    SELECT COUNT(DISTINCT sender_id) FROM req
                    WHERE created_at >= %(s)s AND created_at < %(e)s
                """, {'s': start, 'e': end})
                act_senders = int(cur.fetchone()[0] or 0)
                cur.execute(REQ_CTE + """
                    SELECT COUNT(DISTINCT provider_id) FROM req
                    WHERE d_id IS NOT NULL AND accepted_at >= %(s)s AND accepted_at < %(e)s
                """, {'s': start, 'e': end})
                act_providers = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    WITH per AS (
                        SELECT sender_id, COUNT(*) AS c FROM delivery_requests
                        WHERE created_at >= %(s)s AND created_at < %(e)s GROUP BY sender_id
                    )
                    SELECT COUNT(*) FILTER (WHERE c >= 2), COUNT(*) FROM per
                """, {'s': start, 'e': end})
                rep, tot_s = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM provider_verifications WHERE COALESCE(verification_status, 'Pending') = 'Pending'")
                pending_v = int(cur.fetchone()[0] or 0)

                ctx['usr_kpis'] = [
                    _kpi('New Signups', str(new_u), accent='#34d399', accent2='#d1fae5'),
                    _kpi('Active Senders', str(act_senders), 'Placed a request', '#60a5fa', '#dbeafe'),
                    _kpi('Active Providers', str(act_providers), 'Accepted a delivery', '#FF751F', '#ffedd5'),
                    _kpi('Repeat Booking', _pct_txt(_rate(int(rep or 0), int(tot_s or 0))), '2+ requests per sender',
                         '#c084fc', '#f3e8ff', color='var(--status-success)'),
                    _kpi('Pending Verifications', str(pending_v), 'Provider KYC queue', '#f87171', '#ffe4e6',
                         color='var(--status-danger)'),
                ]

                if role_filter != 'sender':
                    cur.execute(REQ_CTE + """
                        SELECT u.user_id, COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, ''),
                               COUNT(*) FILTER (WHERE r.bucket = 'completed'),
                               COUNT(*),
                               (SELECT AVG(rr.rating) FROM ratings_reviews rr WHERE rr.reviewee_id = u.user_id),
                               (SELECT COUNT(*) FROM ratings_reviews rr WHERE rr.reviewee_id = u.user_id),
                               COALESCE(SUM(COALESCE(t.base_amount, ep.amount, 0)) FILTER (WHERE r.bucket = 'completed'), 0)
                        FROM req r
                        JOIN users u ON u.user_id = r.provider_id
                        LEFT JOIN escrow_payments ep ON ep.delivery_id = r.d_id
                        LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                        WHERE r.d_id IS NOT NULL AND r.accepted_at >= %(s)s AND r.accepted_at < %(e)s
                        GROUP BY u.user_id, u.first_name, u.last_name
                        ORDER BY 3 DESC, 7 DESC
                        LIMIT 5
                    """, {'s': start, 'e': end})
                    for uid, name, comp, acc, avg_r, n_rev, earn in cur.fetchall():
                        ctx['top_providers'].append({
                            'name': (name or '').strip() or f'USR-{uid}',
                            'completed': int(comp or 0), 'accepted': int(acc or 0),
                            'rating': f"{float(avg_r):.1f}" if avg_r is not None else '—',
                            'reviews': int(n_rev or 0),
                            'earnings': _peso(earn),
                        })

            # ======================================================================
            # BLOCKCHAIN
            # ======================================================================
            if tab == 'blockchain':
                bparams = {'s': start, 'e': end}
                pt = ''
                if proof_type != 'all':
                    pt = " AND category = %(pt)s"
                    bparams['pt'] = proof_type

                cur.execute(f"""
                    SELECT COUNT(*) FILTER (WHERE qr.pickup_verified), COUNT(*) FILTER (WHERE qr.dropoff_verified), COUNT(*)
                    FROM qr_verifications qr JOIN deliveries d ON d.delivery_id = qr.delivery_id
                    WHERE d.accepted_at >= %(s)s AND d.accepted_at < %(e)s
                """, bparams)
                qp, qd, qt = [int(x or 0) for x in cur.fetchone()]

                cur.execute(f"SELECT COUNT(*) FROM ({BC_UNION}) sub WHERE recorded_at >= %(s)s AND recorded_at < %(e)s {pt}", bparams)
                total_anch = int(cur.fetchone()[0] or 0)

                cur.execute(f"""
                    SELECT badge, COUNT(*) FROM ({BC_UNION}) sub
                    WHERE recorded_at >= %(s)s AND recorded_at < %(e)s {pt}
                    GROUP BY badge ORDER BY 2 DESC
                """, bparams)
                ctx['bc_modules'] = [{'badge': b, 'count': int(c)} for b, c in cur.fetchall()]

                cur.execute("""
                    SELECT COUNT(*) FROM escrow_payments
                    WHERE bc_escrow_tx_hash IS NOT NULL AND bc_escrow_tx_hash <> ''
                      AND created_at >= %(s)s AND created_at < %(e)s
                """, bparams)
                esc_a = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    SELECT COUNT(*) FROM transactions
                    WHERE bc_tx_hash IS NOT NULL AND bc_tx_hash <> ''
                      AND processed_at >= %(s)s AND processed_at < %(e)s
                """, bparams)
                tx_a = int(cur.fetchone()[0] or 0)
                cur.execute("""
                    SELECT COUNT(*) FROM withdrawal_requests
                    WHERE bc_tx_hash IS NOT NULL AND bc_tx_hash <> ''
                      AND COALESCE(processed_at, requested_at) >= %(s)s AND COALESCE(processed_at, requested_at) < %(e)s
                """, bparams)
                wd_a = int(cur.fetchone()[0] or 0)

                ctx['bc_kpis'] = [
                    _kpi('Total Anchored', str(total_anch), 'Records in period'),
                    _kpi('QR Pickup', _pct_txt(_rate(qp, qt)), 'Verified ÷ QR handoffs', '#34d399', '#d1fae5',
                         color='var(--status-success)'),
                    _kpi('QR Drop-off', _pct_txt(_rate(qd, qt)), 'Verified ÷ QR handoffs', '#34d399', '#d1fae5',
                         color='var(--status-success)'),
                    _kpi('Escrow Anchored', str(esc_a), accent='#60a5fa', accent2='#dbeafe'),
                    _kpi('Financials + Withdrawals', f'{tx_a} + {wd_a}', accent='#c084fc', accent2='#f3e8ff'),
                ]

                bparams['limit'] = 100 if export else 50
                cur.execute(f"""
                    SELECT category, badge, ref_id, entity_name, details, tx_hash, status, recorded_at
                    FROM ({BC_UNION}) sub
                    WHERE recorded_at >= %(s)s AND recorded_at < %(e)s {pt}
                    ORDER BY recorded_at DESC NULLS LAST LIMIT %(limit)s
                """, bparams)
                for cat, badge, ref_id, entity, details, txh, st_txt, rec_at in cur.fetchall():
                    ctx['blockchain_records'].append({
                        'category': cat, 'badge': badge, 'badge_color': BADGE_COLORS.get(badge, 'orange'),
                        'ref_id': ref_id, 'entity_name': entity, 'details': details, 'tx_hash': txh or '',
                        'status': st_txt,
                        'timestamp': rec_at.strftime('%b %d, %Y %I:%M %p') if rec_at else '—',
                    })

    except Exception as e:  # keep the page alive, but SHOW the problem instead of silently rendering zeros
        traceback.print_exc()
        print(f"[reports] DB error: {e}")
        ctx['db_error'] = str(e)
        try:
            connection.rollback()
        except Exception:
            pass

    template = 'pages/reports_print.html' if export else 'pages/reports.html'
    return render(request, template, ctx)