# views/disputes.py
"""
Unified Dispute & Claim Resolution Center (merges disputes.py + escrow_disputes.py).

Combines:
  1. support_tickets (WHERE type = 'dispute')
  2. Standalone legacy disputes (public.disputes not yet linked to a support_ticket)

Provides:
  - 4-point delivery evidence inspector (10-min wait timer, contact attempts, geotagged photos, QR/PIN audit)
  - Sender report + Provider written response
  - Frozen Escrow Verdicts: Rule for Courier (release escrow) / Rule for Sender (refund + Xendit refund)
  - General Case Actions: Resolve with note / Dismiss with reason
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
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from .login import admin_required
from .utils import log_admin_action
from ..blockchain import anchor_escrow_payment

PH_TZ = timezone(timedelta(hours=8))  # Asia/Manila (UTC+8)
PROOF_BUCKET = 'delivery-proofs'
HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Config & HTTP helpers
# ---------------------------------------------------------------------------
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
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f'{name} returned {resp.status_code}: {resp.text[:200]}')
    return resp


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
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
            dt = dt.replace(tzinfo=timezone.utc)
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


def _photo_url(request_id, kind, stored):
    """
    Build a usable photo URL:
      1. If stored is already an http(s) URL, use it.
      2. If SUPABASE_URL is configured, build public proof URL or fall back to signed delivery_photo route.
    """
    if not stored or str(stored).strip().upper() in ('', 'N/A'):
        return None
    s = str(stored).strip()
    if s.lower().startswith(('http://', 'https://')):
        return s
    if request_id and kind in ('pickup', 'pod', 'failure', 'return', 'cargo'):
        try:
            return reverse('delivery_photo', args=[request_id, kind])
        except Exception:
            pass
    cfg = _supabase_cfg()
    base = cfg[0] if cfg else (getattr(settings, 'SUPABASE_URL', None) or os.environ.get('SUPABASE_URL', '')).rstrip('/')
    if base:
        return f"{base}/storage/v1/object/public/{PROOF_BUCKET}/{s.lstrip('/')}"
    return None


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
    if raw in ('on hold', 'on_hold', 'onhold', 'pending', 'held'):
        return 'on_hold'
    return raw or 'pending'


# ---------------------------------------------------------------------------
# Unified Data Loader (support_tickets + standalone public.disputes)
# ---------------------------------------------------------------------------
def _load_unified_disputes(ticket_id=None, dispute_id=None):
    taken_col = 'd.failure_photo_taken_at' if _has_column('deliveries', 'failure_photo_taken_at') else 'NULL::timestamptz'

    where_filter = ""
    params = []
    if ticket_id is not None and int(ticket_id) > 0:
        where_filter = "AND uq.ticket_id = %s"
        params.append(int(ticket_id))
    elif dispute_id is not None and int(dispute_id) > 0:
        where_filter = "AND uq.dispute_id = %s"
        params.append(int(dispute_id))
    elif ticket_id is not None and int(ticket_id) < 0:
        where_filter = "AND uq.dispute_id = %s"
        params.append(abs(int(ticket_id)))

    sql = f"""
        WITH unified_queue AS (
            -- 1) Primary dispute tickets from support_tickets
            SELECT
                st.ticket_id,
                COALESCE(st.legacy_dispute_id, ld.dispute_id) AS dispute_id,
                COALESCE(st.ticket_ref, ld.dispute_ref) AS case_ref,
                st.category,
                st.sub_issue,
                st.description,
                st.requested_resolution,
                st.status AS raw_status,
                COALESCE(st.resolution, ld.resolution) AS resolution,
                COALESCE(st.resolved_at, ld.resolved_at) AS resolved_at,
                st.created_at,
                COALESCE(st.delivery_id, ld.delivery_id) AS delivery_id,
                COALESCE(st.request_id, ld.request_id) AS request_id,
                st.reporter_id,
                st.counterparty_id,
                ld.provider_response,
                ld.provider_responded_at
            FROM support_tickets st
            LEFT JOIN LATERAL (
                SELECT d0.*
                FROM disputes d0
                WHERE (st.legacy_dispute_id IS NOT NULL AND d0.dispute_id = st.legacy_dispute_id)
                   OR (st.legacy_dispute_id IS NULL AND st.request_id IS NOT NULL AND d0.request_id = st.request_id)
                ORDER BY d0.created_at DESC
                LIMIT 1
            ) ld ON TRUE
            WHERE st.type = 'dispute'

            UNION ALL

            -- 2) Standalone rows in public.disputes not linked to any support_ticket
            SELECT
                NULL::bigint AS ticket_id,
                d1.dispute_id,
                d1.dispute_ref AS case_ref,
                'Delivery Dispute'::text AS category,
                d1.issue_type AS sub_issue,
                d1.description,
                NULL::text AS requested_resolution,
                d1.status AS raw_status,
                d1.resolution,
                d1.resolved_at,
                d1.created_at,
                d1.delivery_id,
                d1.request_id,
                d1.reported_by AS reporter_id,
                d1.provider_id AS counterparty_id,
                d1.provider_response,
                d1.provider_responded_at
            FROM disputes d1
            WHERE NOT EXISTS (
                SELECT 1 FROM support_tickets st2
                WHERE st2.type = 'dispute'
                  AND (st2.legacy_dispute_id = d1.dispute_id
                       OR (st2.request_id IS NOT NULL AND st2.request_id = d1.request_id))
            )
        )
        SELECT
            uq.ticket_id,
            uq.dispute_id,
            uq.case_ref,
            uq.category,
            uq.sub_issue,
            uq.description,
            uq.requested_resolution,
            uq.raw_status,
            uq.resolution,
            uq.resolved_at,
            uq.created_at,
            uq.provider_response,
            uq.provider_responded_at,
            COALESCE(uq.delivery_id, d.delivery_id) AS delivery_id,
            uq.request_id,

            dr.estimated_cost, dr.base_fare, dr.return_deposit,
            dr.fallback_action, dr.fallback_recipient_name,
            dr.escrow_status AS req_escrow_status, dr.payment_provider,
            COALESCE(dr.sender_id, uq.reporter_id) AS sender_id,
            cp.description AS cargo_desc,

            CONCAT_WS(' ', su.first_name, su.last_name) AS sender_name,
            su.phone_number AS sender_phone,
            su.email AS sender_email,

            COALESCE(d.provider_id, uq.counterparty_id, dr.preferred_provider_id) AS provider_id,
            CONCAT_WS(' ', pu.first_name, pu.last_name) AS provider_name,
            pu.phone_number AS provider_phone,
            pu.email AS provider_email,

            d.dropoff_arrived_at, d.dropoff_wait_lat, d.dropoff_wait_lng,
            d.call_receiver_at, d.sms_receiver_at, d.chat_sender_at,
            d.failure_reason, d.failure_photo_url, d.failure_photo_lat, d.failure_photo_lng,
            d.failed_at, {taken_col} AS failure_taken_at,
            d.pod_photo_url, d.return_pod_photo_url,

            ep.escrow_id, ep.amount AS ep_amount, ep.escrow_status AS ep_status,
            ep.emergency_frozen, ep.bc_escrow_tx_hash,

            qv.pickup_verified, qv.dropoff_verified, qv.return_verified, qv.return_verified_at,
            (qv.delivery_id IS NOT NULL) AS has_qr
        FROM unified_queue uq
        LEFT JOIN delivery_requests dr ON dr.request_id = uq.request_id
        LEFT JOIN cargo_profiles   cp ON cp.cargo_id = dr.cargo_id
        LEFT JOIN deliveries        d ON (
            (uq.delivery_id IS NOT NULL AND d.delivery_id = uq.delivery_id)
            OR (uq.delivery_id IS NULL AND uq.request_id IS NOT NULL AND d.request_id = uq.request_id)
        )
        LEFT JOIN users su ON su.user_id = COALESCE(dr.sender_id, uq.reporter_id)
        LEFT JOIN users pu ON pu.user_id = COALESCE(d.provider_id, uq.counterparty_id, dr.preferred_provider_id)
        LEFT JOIN LATERAL (
            SELECT escrow_id, amount, escrow_status, emergency_frozen, bc_escrow_tx_hash
            FROM escrow_payments WHERE delivery_id = d.delivery_id
            ORDER BY escrow_id DESC LIMIT 1
        ) ep ON TRUE
        LEFT JOIN LATERAL (
            SELECT delivery_id, pickup_verified, dropoff_verified, return_verified, return_verified_at
            FROM qr_verifications WHERE delivery_id = d.delivery_id
            ORDER BY qr_id DESC LIMIT 1
        ) qv ON TRUE
        WHERE TRUE {where_filter}
        ORDER BY uq.created_at DESC
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _build(r):
    # Canonical ID: positive for support_tickets.ticket_id, negative for standalone disputes.dispute_id
    ticket_id = r['ticket_id']
    dispute_id = r['dispute_id']
    unified_id = ticket_id if ticket_id is not None else (-int(dispute_id) if dispute_id else 0)

    raw_status = (r['raw_status'] or 'Open').strip()
    is_dismissed = raw_status in ('Dismissed', 'Closed')
    is_resolved = raw_status == 'Resolved'
    ticket_open = not (is_resolved or is_dismissed)

    state = _escrow_state(r['ep_status'], r['req_escrow_status'], r['emergency_frozen'])
    state_label_map = {
        'frozen': 'FROZEN',
        'released': 'RELEASED',
        'refunded': 'REFUNDED',
        'on_hold': 'On Hold',
        'pending': 'Pending',
    }
    state_label = state_label_map.get(state, state.replace('_', ' ').title())

    if is_dismissed:
        group = 'dismissed'
    elif is_resolved:
        group = 'resolved'
    elif state == 'frozen':
        group = 'frozen'
    else:
        group = 'open'

    est = r['estimated_cost'] if r['estimated_cost'] is not None else r['ep_amount']
    deposit = r['return_deposit'] or 0
    base = r['base_fare']
    if base is None and est is not None:
        base = max(0.0, float(est) - float(deposit))

    if r['fallback_action'] == 'leave_with_guard':
        fallback = 'Option B \u2013 Leave with guard / receptionist'
        fallback_name = r['fallback_recipient_name'] or 'Name not provided'
    else:
        fallback, fallback_name = 'Option A \u2013 Return to sender', None

    req_id = r['request_id']
    del_id = r['delivery_id']

    # Can settle escrow directly (Release to Courier / Refund Sender) when ticket is open and delivery+request exist
    can_settle_escrow = bool(
        ticket_open
        and del_id
        and req_id
        and state in ('frozen', 'on_hold', 'pending')
    )

    display_ref = (
        r['case_ref']
        or (f"Ticket #{ticket_id}" if ticket_id else f"Case #{dispute_id}")
    )

    return {
        'unified_id': unified_id,
        'ticket_id': ticket_id,
        'dispute_id': dispute_id,
        'case_ref': display_ref,
        'request_id': req_id,
        'delivery_id': del_id,
        'escrow_id': r['escrow_id'],
        'escrow_tx_hash': r['bc_escrow_tx_hash'] or '',
        'provider_id': r['provider_id'],
        'sender_id': r['sender_id'],
        'request_label': f"#PNS-{int(req_id):04d}" if req_id else '\u2014',
        'category': r['category'] or 'Dispute',
        'sub_issue': r['sub_issue'] or 'Reported Issue',
        'description': r['description'] or '',
        'requested_resolution': r['requested_resolution'] or '',
        'provider_response': r['provider_response'] or '',
        'provider_responded_at': fmt_manila(r['provider_responded_at']),
        'status': raw_status,
        'resolution': r['resolution'] or '',
        'resolved_at': fmt_manila(r['resolved_at']),
        'created_at': fmt_manila(r['created_at']),
        'created_iso': r['created_at'].isoformat() if r['created_at'] else None,
        'resolved_iso': r['resolved_at'].isoformat() if r['resolved_at'] else None,
        'cargo_desc': r['cargo_desc'] or '',
        'payment_provider': (r['payment_provider'] or '').upper() or '\u2014',

        'state': state,
        'state_label': state_label,
        'group': group,
        'is_open': ticket_open,
        'can_act': can_settle_escrow,
        'can_note_resolve': ticket_open,

        'total_held': _money(est),
        'base_fare': _money(base),
        'return_deposit': _money(deposit),
        'fallback': fallback,
        'fallback_name': fallback_name,

        'sender_name': _name(r['sender_name'], f"USR-{r['sender_id']}" if r['sender_id'] else 'Unknown sender'),
        'sender_phone': r['sender_phone'] or '\u2014',
        'sender_email': r['sender_email'] or '\u2014',
        'provider_name': _name(r['provider_name'], f"USR-{r['provider_id']}" if r['provider_id'] else 'No courier assigned'),
        'provider_phone': r['provider_phone'] or '\u2014',
        'provider_email': r['provider_email'] or '\u2014',

        'arrived_at': fmt_manila(r['dropoff_arrived_at']),
        'wait_lat': r['dropoff_wait_lat'],
        'wait_lng': r['dropoff_wait_lng'],
        'wait_map': _maps(r['dropoff_wait_lat'], r['dropoff_wait_lng']),

        'contacts': [
            {'label': 'Called the receiver', 'ok': bool(r['call_receiver_at']), 'at': fmt_manila(r['call_receiver_at'])},
            {'label': 'Texted the receiver (SMS)', 'ok': bool(r['sms_receiver_at']), 'at': fmt_manila(r['sms_receiver_at'])},
            {'label': 'Chatted with the sender', 'ok': bool(r['chat_sender_at']), 'at': fmt_manila(r['chat_sender_at'])},
        ],

        'failure_reason': r['failure_reason'] or '',
        'failure_photo': _photo_url(req_id, 'failure', r['failure_photo_url']),
        'failure_photo_raw': r['failure_photo_url'] or '',
        'failure_lat': r['failure_photo_lat'],
        'failure_lng': r['failure_photo_lng'],
        'failure_map': _maps(r['failure_photo_lat'], r['failure_photo_lng']),
        'failure_taken_at': fmt_manila(r['failure_taken_at'] or r['failed_at']),
        'pod_photo': _photo_url(req_id, 'pod', r['pod_photo_url']),
        'return_pod_photo': _photo_url(req_id, 'return', r['return_pod_photo_url']),

        'has_qr': bool(r['has_qr']),
        'qr': [
            {'label': 'Pickup QR', 'ok': bool(r['pickup_verified']), 'at': None},
            {'label': 'Drop-off QR', 'ok': bool(r['dropoff_verified']), 'at': None},
            {'label': 'Return-to-sender QR', 'ok': bool(r['return_verified']), 'at': fmt_manila(r['return_verified_at'])},
        ],
    }


# ---------------------------------------------------------------------------
# Unified Page View (serves both /disputes/ and /escrow-disputes/)
# ---------------------------------------------------------------------------
@admin_required
def admin_disputes_view(request):
    current_tab = request.GET.get('tab', 'open')
    if current_tab not in ('open', 'frozen', 'resolved', 'dismissed', 'all'):
        current_tab = 'open'
    initial_q = (request.GET.get('q') or request.GET.get('delivery_id') or '').strip()

    all_tickets, error = [], None
    try:
        all_tickets = [_build(r) for r in _load_unified_disputes()]
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'[disputes] Database query error: {e}')
        error = str(e)

    counts = {
        'all': len(all_tickets),
        'frozen': sum(1 for t in all_tickets if t['group'] == 'frozen'),
        'open': sum(1 for t in all_tickets if t['is_open']),
        'resolved': sum(1 for t in all_tickets if t['group'] == 'resolved'),
        'dismissed': sum(1 for t in all_tickets if t['group'] == 'dismissed'),
    }

    if current_tab == 'all':
        tickets = all_tickets
    elif current_tab == 'open':
        tickets = [t for t in all_tickets if t['is_open']]
    else:
        tickets = [t for t in all_tickets if t['group'] == current_tab]

    return render(request, 'pages/admin_disputes.html', {
        'current_tab': current_tab,
        'tickets': tickets,
        'counts': counts,
        'error': error,
        'initial_q': initial_q,
    })


# Alias so existing urls.py / imports pointing to escrow_disputes work identically
escrow_disputes = admin_disputes_view


# ---------------------------------------------------------------------------
# Unified Action Endpoint: Courier Verdict / Sender Verdict / Resolve / Dismiss
# ---------------------------------------------------------------------------
def _notify_parties_in_db(cur, sender_id, provider_id, title, body, ref_id):
    for uid in (sender_id, provider_id):
        if uid:
            cur.execute(
                """
                INSERT INTO notification_log (user_id, title, body, type, ref_id)
                VALUES (%s, %s, %s, 'dispute', %s)
                """,
                [uid, title, body[:180], ref_id or 0],
            )


@admin_required
@require_POST
def resolve_dispute(request, ticket_id):
    """
    Handles all 4 dispute resolution outcomes:
      - outcome == 'courier' : Unfreeze & release escrow to courier wallet + mark Resolved
      - outcome == 'sender'  : Refund escrow to sender + trigger Xendit refund + mark Resolved
      - outcome == 'resolve' : Mark dispute/ticket Resolved with custom admin note
      - outcome == 'dismiss' : Mark dispute/ticket Dismissed/Closed with custom admin reason
    """
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    outcome = (payload.get('outcome') or '').strip().lower()
    custom_note = (payload.get('resolution') or payload.get('note') or '').strip()

    if outcome not in ('courier', 'sender', 'resolve', 'dismiss'):
        return JsonResponse({'error': 'Unknown resolution outcome.'}, status=400)

    try:
        rows = _load_unified_disputes(ticket_id=int(ticket_id))
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    if not rows:
        return JsonResponse({'error': 'Dispute case not found.'}, status=404)

    t = _build(rows[0])
    if not t['is_open']:
        return JsonResponse({'error': 'This dispute case is already closed.'}, status=409)

    warnings = []
    tx_hash = ''

    # =========================================================================
    # A) ESCROW VERDICTS ('courier' or 'sender')
    # =========================================================================
    if outcome in ('courier', 'sender'):
        if not t['can_act']:
            return JsonResponse({
                'error': 'Escrow settlement is not available for this case (missing delivery or escrow already settled).'
            }, status=409)

        if outcome == 'courier':
            rpc_outcome = 'resolve_dispute_release'
            default_res = 'Ruled in favor of the courier. Escrow unfrozen and released to the provider wallet.'
            resolution = f"{default_res} Note: {custom_note}" if custom_note else default_res
            message = 'Escrow unfrozen and released to the Provider wallet.'
            log_verdict = 'in favor of the Courier (escrow released)'
        else:
            rpc_outcome = 'resolve_dispute_refund'
            default_res = 'Ruled in favor of the sender. Escrow refunded; payout withheld from the courier.'
            resolution = f"{default_res} Note: {custom_note}" if custom_note else default_res
            message = 'Sender refunded and dispute marked Resolved.'
            log_verdict = 'in favor of the Sender (escrow refunded)'

        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT public.settle_delivery_escrow(p_delivery_id => %s, p_outcome => %s)",
                        [t['delivery_id'], rpc_outcome],
                    )
                    if t['ticket_id']:
                        cur.execute(
                            """
                            UPDATE support_tickets
                               SET status = 'Resolved', resolution = %s, resolved_at = NOW(),
                                   updated_at = NOW(), last_activity_at = NOW()
                             WHERE ticket_id = %s AND status NOT IN ('Resolved', 'Closed')
                            """,
                            [resolution, t['ticket_id']],
                        )
                        cur.execute(
                            "INSERT INTO ticket_events (ticket_id, status, note) VALUES (%s, 'Resolved', %s)",
                            [t['ticket_id'], resolution],
                        )
                    if t['dispute_id']:
                        cur.execute(
                            """
                            UPDATE disputes
                               SET status = 'Resolved', resolution = %s, resolved_at = NOW(), updated_at = NOW()
                             WHERE dispute_id = %s
                            """,
                            [resolution, t['dispute_id']],
                        )
                    elif t['request_id']:
                        cur.execute(
                            """
                            UPDATE disputes
                               SET status = 'Resolved', resolution = %s, resolved_at = NOW(), updated_at = NOW()
                             WHERE request_id = %s AND status NOT IN ('Resolved', 'Dismissed')
                            """,
                            [resolution, t['request_id']],
                        )

                    _notify_parties_in_db(
                        cur,
                        t['sender_id'],
                        t['provider_id'],
                        f"Dispute {t['case_ref']} resolved",
                        resolution,
                        t['dispute_id'] or t['ticket_id'],
                    )
        except Exception as e:
            return JsonResponse({'error': f'Nothing was changed. {e}'}, status=400)

        # Anchor settled escrow on-chain
        if t['escrow_id']:
            try:
                with transaction.atomic():
                    with connection.cursor() as cur:
                        tx_hash = anchor_escrow_payment(cur, t['escrow_id']) or ''
            except Exception as e:
                warnings.append(f'Verdict saved, but the blockchain anchor failed: {e}')

        # Admin audit log
        try:
            short = f' [Tx: {tx_hash[:18]}...]' if tx_hash else ''
            log_admin_action(
                request,
                f"Resolved dispute {t['case_ref']} ({t['request_label']}) {log_verdict}"
                f"{' EID' + str(t['escrow_id']) if t['escrow_id'] else ''}, {t['total_held']}{short}",
            )
        except Exception as e:
            print(f'[disputes] log_admin_action failed: {e}')

        # Trigger live Xendit refund on sender verdict
        if outcome == 'sender' and t['request_id']:
            try:
                _post_function('xendit-refund', {'request_id': t['request_id'], 'reason': 'FRAUDULENT'})
            except Exception as e:
                warnings.append(
                    f'The ledger is marked Refunded, but the Xendit refund call failed ({e}). '
                    'If this is the sandbox, mark the refund manually.'
                )

        # Best-effort push notifications
        ref = t['request_label'].lstrip('#')
        push_data = {'type': 'dispute_resolved', 'requestId': t['request_id'], 'ticketId': t['ticket_id']}
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
        for uid, p_title, p_body, role in msgs:
            if not uid:
                continue
            try:
                _post_function('send-push', {'user_id': uid, 'title': p_title, 'body': p_body, 'data': {**push_data, 'role': role}}, timeout=8)
            except Exception as e:
                print(f'[disputes] push to user {uid} skipped: {e}')

        return JsonResponse({'status': 'success', 'message': message, 'warnings': warnings})

    # =========================================================================
    # B) GENERAL RESOLVE / DISMISS WITH NOTE ('resolve' or 'dismiss')
    # =========================================================================
    if len(custom_note) < 5:
        return JsonResponse({'error': 'Please provide a resolution/dismissal note (at least 5 characters).'}, status=400)

    is_dismiss = (outcome == 'dismiss')
    new_dispute_status = 'Dismissed' if is_dismiss else 'Resolved'
    new_ticket_status = 'Closed' if is_dismiss else 'Resolved'
    action_word = 'Dismissed' if is_dismiss else 'Resolved'

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                if t['ticket_id']:
                    cur.execute(
                        """
                        UPDATE support_tickets
                           SET status = %s, resolution = %s, resolved_at = NOW(),
                               updated_at = NOW(), last_activity_at = NOW()
                         WHERE ticket_id = %s
                        """,
                        [new_ticket_status, custom_note, t['ticket_id']],
                    )
                    cur.execute(
                        "INSERT INTO ticket_events (ticket_id, status, note) VALUES (%s, %s, %s)",
                        [t['ticket_id'], new_ticket_status, custom_note],
                    )
                if t['dispute_id']:
                    cur.execute(
                        """
                        UPDATE disputes
                           SET status = %s, resolution = %s, resolved_at = NOW(), updated_at = NOW()
                         WHERE dispute_id = %s
                        """,
                        [new_dispute_status, custom_note, t['dispute_id']],
                    )
                elif t['request_id']:
                    cur.execute(
                        """
                        UPDATE disputes
                           SET status = %s, resolution = %s, resolved_at = NOW(), updated_at = NOW()
                         WHERE request_id = %s AND status NOT IN ('Resolved', 'Dismissed')
                        """,
                        [new_dispute_status, custom_note, t['request_id']],
                    )

                _notify_parties_in_db(
                    cur,
                    t['sender_id'],
                    t['provider_id'],
                    f"Dispute {t['case_ref']} {action_word.lower()}",
                    custom_note,
                    t['dispute_id'] or t['ticket_id'],
                )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    log_admin_action(request, f"{action_word} Dispute {t['case_ref']} ({t['request_label']}): {custom_note[:80]}")

    return JsonResponse({
        'status': 'success',
        'new_status': new_dispute_status,
        'message': f"Case {t['case_ref']} marked as {new_dispute_status}.",
        'warnings': [],
    })


# ---------------------------------------------------------------------------
# Legacy JSON API endpoints (preserved so existing API routes remain valid)
# ---------------------------------------------------------------------------
@admin_required
@require_http_methods(["GET"])
def disputes_list_api(request):
    tab = request.GET.get('tab', 'open')
    search = (request.GET.get('q') or '').strip().lower()
    items = [_build(r) for r in _load_unified_disputes()]

    if tab == 'open':
        items = [i for i in items if i['is_open']]
    elif tab in ('frozen', 'resolved', 'dismissed'):
        items = [i for i in items if i['group'] == tab]

    if search:
        items = [
            i for i in items
            if search in f"{i['case_ref']} {i['request_label']} {i['sub_issue']} {i['description']} {i['sender_name']} {i['provider_name']}".lower()
        ]

    return JsonResponse({'disputes': items, 'tab': tab})


@admin_required
@require_http_methods(["GET"])
def dispute_detail_api(request, dispute_id):
    rows = _load_unified_disputes(dispute_id=dispute_id)
    if not rows:
        rows = _load_unified_disputes(ticket_id=dispute_id)
    if not rows:
        return JsonResponse({'error': 'Dispute not found'}, status=404)
    return JsonResponse({'dispute': _build(rows[0])})


@admin_required
@require_POST
def dispute_resolve_api(request, dispute_id):
    rows = _load_unified_disputes(dispute_id=dispute_id)
    target_id = _build(rows[0])['unified_id'] if rows else dispute_id
    try:
        body = json.loads(request.body or '{}')
    except Exception:
        body = {}
    body['outcome'] = body.get('outcome') or 'resolve'
    request._body = json.dumps(body).encode('utf-8')
    return resolve_dispute(request, target_id)


@admin_required
@require_POST
def dispute_dismiss_api(request, dispute_id):
    rows = _load_unified_disputes(dispute_id=dispute_id)
    target_id = _build(rows[0])['unified_id'] if rows else dispute_id
    try:
        body = json.loads(request.body or '{}')
    except Exception:
        body = {}
    body['outcome'] = 'dismiss'
    request._body = json.dumps(body).encode('utf-8')
    return resolve_dispute(request, target_id)