# views/escrow_disputes.py
"""
Escrow Disputes & Frozen Deliveries (admin web).

Queue   : support_tickets WHERE type = 'dispute', joined with the delivery, escrow, parties and QR rows.
Inspector: evidence blocks (10-min wait timer, contact attempts, geotagged proof, QR audit).
Verdicts : call the existing Postgres function  settle_delivery_escrow(p_delivery_id, p_outcome)
           and close the ticket in ONE database transaction (all-or-nothing), then anchor the escrow on the
           blockchain ledger, write the admin log, trigger the Xendit refund (sender verdict) and notify both parties.

Same conventions as escrow_payments.py: raw SQL via django.db.connection, @admin_required, log_admin_action,
anchor_escrow_payment.

Optional settings (only needed for the Xendit refund, push notifications and relative photo paths):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   (Django settings or environment variables)
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .login import admin_required
from .utils import log_admin_action
from ..blockchain import anchor_escrow_payment

PH_TZ = timezone(timedelta(hours=8))  # Asia/Manila - no DST, so a fixed offset is exact on every OS
PROOF_BUCKET = 'delivery-proofs'
HTTP_TIMEOUT = 20


# --------------------------------------------------------------------------- config / http helpers
def _supabase_cfg():
    url = (getattr(settings, 'SUPABASE_URL', None) or os.environ.get('SUPABASE_URL', '')).rstrip('/')
    key = getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', None) or os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    return (url, key) if url and key else None


def _post_function(name, payload, timeout=HTTP_TIMEOUT):
    cfg = _supabase_cfg()
    if not cfg:
        raise RuntimeError('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set for the admin site.')
    url, key = cfg
    resp = requests.post(
        f'{url}/functions/v1/{name}',
        headers={'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json=payload, timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f'{name} returned {resp.status_code}: {resp.text[:200]}')
    return resp


# --------------------------------------------------------------------------- formatting helpers
def fmt_manila(v):
    """datetime / ISO string -> 'Nov 10, 2026, 07:35:12 PM PHT'. None when empty."""
    if not v:
        return None
    try:
        if isinstance(v, datetime):
            dt = v
        else:
            s = str(v).replace('Z', '+00:00')
            s = re.sub(r'(\.\d+)', lambda m: (m.group(1) + '000000')[:7], s, count=1)
            dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # naive Supabase columns are stored in UTC
        return dt.astimezone(PH_TZ).strftime('%b %d, %Y, %I:%M:%S %p') + ' PHT'
    except Exception:
        return str(v)


def _money(v):
    try:
        return f'\u20b1{float(v):,.2f}'
    except (TypeError, ValueError):
        return '\u20b10.00'


def _name(n, fallback):
    n = (n or '').strip()
    return n or fallback


def _public_url(path):
    if not path:
        return None
    if str(path).startswith('http'):
        return path
    cfg = _supabase_cfg()
    base = cfg[0] if cfg else (getattr(settings, 'SUPABASE_URL', None) or os.environ.get('SUPABASE_URL', '')).rstrip('/')
    if not base:
        return None  # relative path and no project URL to build the link from
    return f"{base}/storage/v1/object/public/{PROOF_BUCKET}/{str(path).lstrip('/')}"


def _maps(lat, lng):
    return f'https://www.google.com/maps?q={lat},{lng}' if lat is not None and lng is not None else None


def _has_column(table, column):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
            [table, column],
        )
        return cur.fetchone() is not None


def _escrow_state(ep_status, req_status, frozen):
    raw = (ep_status or req_status or '').strip().lower()
    if raw in ('released', 'completed'):
        return 'released'
    if raw == 'refunded':
        return 'refunded'
    if frozen or raw == 'frozen':
        return 'frozen'
    return raw or 'pending'


# --------------------------------------------------------------------------- data
def _load_disputes(ticket_id=None):
    taken_col = 'd.failure_photo_taken_at' if _has_column('deliveries', 'failure_photo_taken_at') else 'NULL::timestamptz'
    sql = f"""
        SELECT
            st.ticket_id, st.category, st.sub_issue, st.description, st.requested_resolution,
            st.status, st.resolution, st.resolved_at, st.created_at, st.delivery_id, st.request_id,
            dr.estimated_cost, dr.base_fare, dr.return_deposit, dr.fallback_action, dr.fallback_recipient_name,
            dr.escrow_status AS req_escrow_status, dr.payment_provider, dr.sender_id,
            cp.description AS cargo_desc,
            CONCAT_WS(' ', su.first_name, su.last_name) AS sender_name, su.phone_number AS sender_phone,
            d.provider_id,
            CONCAT_WS(' ', pu.first_name, pu.last_name) AS provider_name, pu.phone_number AS provider_phone,
            d.dropoff_arrived_at, d.dropoff_wait_lat, d.dropoff_wait_lng,
            d.call_receiver_at, d.sms_receiver_at, d.chat_sender_at,
            d.failure_reason, d.failure_photo_url, d.failure_photo_lat, d.failure_photo_lng,
            d.failed_at, {taken_col} AS failure_taken_at,
            d.pod_photo_url, d.return_pod_photo_url,
            ep.escrow_id, ep.escrow_status AS ep_status, ep.emergency_frozen,
            qv.pickup_verified, qv.dropoff_verified, qv.return_verified, qv.return_verified_at,
            (qv.delivery_id IS NOT NULL) AS has_qr
        FROM support_tickets st
        LEFT JOIN delivery_requests dr ON dr.request_id = st.request_id
        LEFT JOIN cargo_profiles   cp ON cp.cargo_id = dr.cargo_id
        LEFT JOIN users            su ON su.user_id = dr.sender_id
        LEFT JOIN deliveries        d ON d.delivery_id = st.delivery_id
        LEFT JOIN users            pu ON pu.user_id = d.provider_id
        LEFT JOIN LATERAL (
            SELECT escrow_id, escrow_status, emergency_frozen
            FROM escrow_payments WHERE delivery_id = d.delivery_id
            ORDER BY escrow_id DESC LIMIT 1
        ) ep ON TRUE
        LEFT JOIN LATERAL (
            SELECT delivery_id, pickup_verified, dropoff_verified, return_verified, return_verified_at
            FROM qr_verifications WHERE delivery_id = d.delivery_id
            ORDER BY qr_id DESC LIMIT 1
        ) qv ON TRUE
        WHERE st.type = 'dispute' {'AND st.ticket_id = %s' if ticket_id is not None else ''}
        ORDER BY st.created_at DESC
    """
    with connection.cursor() as cur:
        cur.execute(sql, [ticket_id] if ticket_id is not None else [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _build(r):
    state = _escrow_state(r['ep_status'], r['req_escrow_status'], r['emergency_frozen'])
    ticket_open = (r['status'] or '') not in ('Resolved', 'Closed')

    est = r['estimated_cost']
    deposit = r['return_deposit'] or 0
    base = r['base_fare']
    if base is None and est is not None:
        base = float(est) - float(deposit)

    if r['fallback_action'] == 'leave_with_guard':
        fallback = 'Option B \u2013 Leave with guard / receptionist'
        fallback_name = r['fallback_recipient_name'] or 'Name not provided'
    else:
        fallback, fallback_name = 'Option A \u2013 Return to sender', None

    return {
        'ticket_id': r['ticket_id'],
        'request_id': r['request_id'],
        'delivery_id': r['delivery_id'],
        'escrow_id': r['escrow_id'],
        'provider_id': r['provider_id'],
        'sender_id': r['sender_id'],
        'request_label': f"#PNS-{int(r['request_id']):04d}" if r['request_id'] else '\u2014',
        'category': r['category'], 'sub_issue': r['sub_issue'],
        'description': r['description'], 'requested_resolution': r['requested_resolution'],
        'status': r['status'], 'resolution': r['resolution'],
        'resolved_at': fmt_manila(r['resolved_at']), 'created_at': fmt_manila(r['created_at']),
        'cargo_desc': r['cargo_desc'], 'payment_provider': r['payment_provider'],

        'state': state,
        'state_label': state.upper() if state in ('frozen', 'released', 'refunded') else state.title(),
        'group': 'resolved' if not ticket_open else ('frozen' if state == 'frozen' else 'open'),
        'can_act': bool(ticket_open and state == 'frozen' and r['delivery_id'] and r['request_id']),

        'total_held': _money(est), 'base_fare': _money(base), 'return_deposit': _money(deposit),
        'fallback': fallback, 'fallback_name': fallback_name,

        'sender_name': _name(r['sender_name'], 'Unknown sender'), 'sender_phone': r['sender_phone'] or '\u2014',
        'provider_name': _name(r['provider_name'], 'No courier assigned'), 'provider_phone': r['provider_phone'] or '\u2014',

        'arrived_at': fmt_manila(r['dropoff_arrived_at']),
        'wait_lat': r['dropoff_wait_lat'], 'wait_lng': r['dropoff_wait_lng'],
        'wait_map': _maps(r['dropoff_wait_lat'], r['dropoff_wait_lng']),

        'contacts': [
            {'label': 'Called the receiver', 'ok': bool(r['call_receiver_at']), 'at': fmt_manila(r['call_receiver_at'])},
            {'label': 'Texted the receiver (SMS)', 'ok': bool(r['sms_receiver_at']), 'at': fmt_manila(r['sms_receiver_at'])},
            {'label': 'Chatted with the sender', 'ok': bool(r['chat_sender_at']), 'at': fmt_manila(r['chat_sender_at'])},
        ],

        'failure_reason': r['failure_reason'],
        'failure_photo': _public_url(r['failure_photo_url']),
        'failure_photo_raw': r['failure_photo_url'],
        'failure_lat': r['failure_photo_lat'], 'failure_lng': r['failure_photo_lng'],
        'failure_map': _maps(r['failure_photo_lat'], r['failure_photo_lng']),
        'failure_taken_at': fmt_manila(r['failure_taken_at'] or r['failed_at']),
        'pod_photo': _public_url(r['pod_photo_url']),
        'return_pod_photo': _public_url(r['return_pod_photo_url']),

        'has_qr': bool(r['has_qr']),
        'qr': [
            {'label': 'Pickup QR', 'ok': bool(r['pickup_verified']), 'at': None},
            {'label': 'Drop-off QR', 'ok': bool(r['dropoff_verified']), 'at': None},
            {'label': 'Return-to-sender QR', 'ok': bool(r['return_verified']), 'at': fmt_manila(r['return_verified_at'])},
        ],
    }


# --------------------------------------------------------------------------- views
@admin_required
def escrow_disputes(request):
    current_tab = request.GET.get('tab', 'open')
    if current_tab not in ('open', 'frozen', 'resolved', 'all'):
        current_tab = 'open'

    all_tickets, error = [], None
    try:
        all_tickets = [_build(r) for r in _load_disputes()]
    except Exception as e:
        print(f'[escrow_disputes] Database query error: {e}')
        error = str(e)

    counts = {
        'all': len(all_tickets),
        'frozen': sum(1 for t in all_tickets if t['group'] == 'frozen'),
        'open': sum(1 for t in all_tickets if t['group'] != 'resolved'),
        'resolved': sum(1 for t in all_tickets if t['group'] == 'resolved'),
    }
    if current_tab == 'all':
        tickets = all_tickets
    elif current_tab == 'open':
        tickets = [t for t in all_tickets if t['group'] != 'resolved']
    else:
        tickets = [t for t in all_tickets if t['group'] == current_tab]

    return render(request, 'pages/escrow_disputes.html', {
        'current_tab': current_tab, 'tickets': tickets, 'counts': counts, 'error': error,
    })


@admin_required
@require_POST
def resolve_dispute(request, ticket_id):
    """
    outcome 'courier' -> settle_delivery_escrow(..., 'resolve_dispute_release')
    outcome 'sender'  -> settle_delivery_escrow(..., 'resolve_dispute_refund') + xendit-refund
    The ticket is re-read here so the browser cannot choose ids or re-apply a verdict.
    """
    try:
        outcome = json.loads(request.body or '{}').get('outcome')
    except ValueError:
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    if outcome not in ('courier', 'sender'):
        return JsonResponse({'error': 'Unknown verdict.'}, status=400)

    try:
        rows = _load_disputes(int(ticket_id))
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
    if not rows:
        return JsonResponse({'error': 'Dispute ticket not found.'}, status=404)
    t = _build(rows[0])
    if t['group'] == 'resolved':
        return JsonResponse({'error': 'This dispute is already resolved.'}, status=409)
    if not t['can_act']:
        return JsonResponse({'error': 'Escrow is not frozen for this delivery, so there is nothing to settle.'}, status=409)

    if outcome == 'courier':
        rpc_outcome = 'resolve_dispute_release'
        resolution = 'Ruled in favor of the courier. Escrow unfrozen and released to the provider wallet.'
        message = 'Escrow unfrozen and released to the Provider wallet.'
        log_verdict = 'in favor of the Courier (escrow released)'
    else:
        rpc_outcome = 'resolve_dispute_refund'
        resolution = 'Ruled in favor of the sender. Escrow refunded; payout withheld from the courier.'
        message = 'Sender refunded and dispute marked Resolved.'
        log_verdict = 'in favor of the Sender (escrow refunded)'

    # 1) Ledger + ticket in ONE transaction: if either step fails, nothing is changed.
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT public.settle_delivery_escrow(p_delivery_id => %s, p_outcome => %s)",
                    [t['delivery_id'], rpc_outcome],
                )
                cur.execute(
                    """
                    UPDATE support_tickets
                       SET status = 'Resolved', resolution = %s, resolved_at = NOW(),
                           updated_at = NOW(), last_activity_at = NOW()
                     WHERE ticket_id = %s AND status NOT IN ('Resolved', 'Closed')
                    """,
                    [resolution, t['ticket_id']],
                )
                if cur.rowcount == 0:
                    raise RuntimeError('This dispute was already resolved by someone else.')
                cur.execute(
                    "INSERT INTO ticket_events (ticket_id, status, note) VALUES (%s, 'Resolved', %s)",
                    [t['ticket_id'], resolution],
                )
    except Exception as e:
        return JsonResponse({'error': f'Nothing was changed. {e}'}, status=400)

    warnings = []

    # 2) Anchor the settled escrow on the blockchain ledger (same as the Escrow & Payments page).
    tx_hash = ''
    if t['escrow_id']:
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    tx_hash = anchor_escrow_payment(cur, t['escrow_id']) or ''
        except Exception as e:
            warnings.append(f'Verdict saved, but the blockchain anchor failed: {e}')

    # 3) Admin audit log.
    try:
        short = f' [Tx: {tx_hash[:18]}...]' if tx_hash else ''
        log_admin_action(
            request,
            f"Resolved dispute Ticket #{t['ticket_id']} ({t['request_label']}) {log_verdict}"
            f"{' EID' + str(t['escrow_id']) if t['escrow_id'] else ''}, {t['total_held']}{short}",
        )
    except Exception as e:
        print(f'[escrow_disputes] log_admin_action failed: {e}')

    # 4) Sender verdict: trigger the live Xendit refund. Failure is a warning, not a rollback (ledger is already settled).
    if outcome == 'sender':
        try:
            _post_function('xendit-refund', {'request_id': t['request_id'], 'reason': 'FRAUDULENT'})
        except Exception as e:
            warnings.append(f'The ledger is marked Refunded, but the Xendit refund call failed ({e}). '
                            'If this is the sandbox, mark the refund manually.')

    # 5) Tell both parties (best effort).
    ref = t['request_label'].lstrip('#')
    data = {'type': 'dispute_resolved', 'requestId': t['request_id'], 'ticketId': t['ticket_id']}
    if outcome == 'courier':
        msgs = [
            (t['sender_id'], 'Dispute resolved', f'Your dispute for parcel #{ref} was reviewed. The payment was released to the courier.', 'sender'),
            (t['provider_id'], 'Dispute resolved in your favor', f'The dispute for parcel #{ref} was resolved. Your payout has been released.', 'provider'),
        ]
    else:
        msgs = [
            (t['sender_id'], 'Dispute resolved in your favor', f'Your dispute for parcel #{ref} was upheld. A full refund is on its way.', 'sender'),
            (t['provider_id'], 'Dispute resolved', f"The dispute for parcel #{ref} was resolved in the sender's favor. No payout will be released.", 'provider'),
        ]
    for uid, title, body, role in msgs:
        if not uid:
            continue
        try:
            _post_function('send-push', {'user_id': uid, 'title': title, 'body': body, 'data': {**data, 'role': role}}, timeout=8)
        except Exception as e:
            print(f'[escrow_disputes] push to user {uid} skipped: {e}')

    return JsonResponse({'status': 'success', 'message': message, 'warnings': warnings})