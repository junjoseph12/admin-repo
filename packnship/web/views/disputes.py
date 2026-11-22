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
  - Provider strikes MERGED into the ruling: "Rule for Sender" (or "Resolve with note") can issue
    a strike to the courier in the SAME database transaction as the refund / resolution.
  - "Refund Sender (Escrow Already Released)": for damaged / wrong-item / not-received reports that arrive AFTER
    the payout was released. The sender is refunded through Xendit and the amount is recovered from the courier's
    wallet (the admin chooses the amount; the wallet may go negative until future earnings cover it).
  - Refund tracking: escrow ledger vs. the real Xendit refund, with a "Retry refund" action so a
    failed Xendit call never leaves the sender un-refunded.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from .login import admin_required
from .strikes import (
    DEFAULT_SUSPENSION_DAYS,
    REASON_CATEGORIES,
    REMOVAL_POINTS,
    SUSPENSION_DAY_OPTIONS,
    StrikeError,
    _issue_strike_tx,
    _issuer_id,
    _log_strike,
    consequence_for,
)
from .utils import log_admin_action
from ..blockchain import anchor_escrow_payment

PH_TZ = timezone(timedelta(hours=8))  # Asia/Manila (UTC+8)
PROOF_BUCKET = 'delivery-proofs'
HTTP_TIMEOUT = 20

# Reason sent to Xendit. NEVER use 'FRAUDULENT' here: it flags the sender's payment as fraud.
REFUND_REASON = 'REQUESTED_BY_CUSTOMER'

# delivery_requests.refund_status values (Xendit refund statuses), compared upper-cased.
REFUND_OK_STATUSES = {'SUCCEEDED', 'SUCCESS', 'COMPLETED', 'REFUNDED'}
REFUND_PENDING_STATUSES = {'PENDING', 'REQUESTED', 'PROCESSING', 'ACCEPTED'}
REFUND_FAILED_STATUSES = {'FAILED', 'CANCELLED', 'CANCELED', 'EXPIRED', 'REJECTED', 'ERROR'}


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


class DisputeError(StrikeError):
    """A user-facing validation error raised inside a dispute transaction."""


def _refund_error_hint(err):
    """Turn a raw refund error into the most likely cause, so the admin knows what to fix."""
    e = str(err or '')
    low = e.lower()
    if 'are not set for the admin site' in low:
        return ('The admin site has no Supabase keys. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the '
                'environment (or settings.py) of this Django server, then restart it.')
    if ' 404' in low or 'function not found' in low or 'not_found' in low:
        return 'The edge function "xendit-refund" is not deployed in this Supabase project (or has another name).'
    if ' 401' in low or ' 403' in low or 'jwt' in low or 'unauthor' in low:
        return ('Supabase rejected the admin key. Check SUPABASE_SERVICE_ROLE_KEY and whether the xendit-refund '
                'function requires a signed-in user instead of the service key.')
    if 'cannot refund' in low and 'status was' in low:
        return ('The xendit-refund function refuses to refund a request that is already marked refunded. The ruling '
                'sets the escrow to refunded BEFORE the money is sent, so the function\'s guard must allow a refund '
                'when refund_status is empty (the money has not actually moved yet). Fix the guard in the edge function.')
    if 'timed out' in low or 'timeout' in low or 'connection' in low:
        return 'Could not reach Supabase from the admin server (network or timeout). Try again.'
    if any(k in low for k in ('not supported', 'unsupported', 'sandbox', 'payment_request', 'not found', 'invalid')):
        return ('Xendit refused the refund. In test (sandbox) mode, GCash/Maya refunds are often not supported. '
                'Check the xendit-refund function logs in Supabase for the exact Xendit message.')
    return 'Check the xendit-refund function logs in Supabase (Edge Functions > xendit-refund > Logs).'


def _extract_refund_fields(body):
    """
    Find a refund id and refund status in whatever shape the edge function answers with.
    A bare top-level "status": "success" is NOT a refund status, so it is only trusted when an id is present.
    """
    if not isinstance(body, dict):
        return None, None
    inner = body.get('refund') if isinstance(body.get('refund'), dict) else (
        body.get('data') if isinstance(body.get('data'), dict) else {})
    rid = (body.get('refund_id') or body.get('refundId') or inner.get('refund_id')
           or inner.get('id') or body.get('id'))
    st = body.get('refund_status') or inner.get('refund_status') or inner.get('status')
    if not st and rid and isinstance(body.get('status'), str):
        st = body.get('status')
    return (str(rid) if rid else None), (str(st) if st else None)


def _save_refund_result(request_id, refund_id, refund_status):
    """Persist what Xendit answered, so the case shows the real refund status."""
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                UPDATE delivery_requests
                   SET refund_id = COALESCE(%s, refund_id),
                       refund_status = COALESCE(%s, refund_status),
                       refund_requested_at = COALESCE(refund_requested_at, NOW())
                 WHERE request_id = %s
                """,
                [refund_id, refund_status, request_id],
            )
    except Exception as e:
        print(f'[disputes] could not save refund result: {e}')


def _xendit_refund_call(request_id, amount=None, is_dispute_refund=True):
    """
    Ask the xendit-refund edge function to return the sender's money.
    Supports partial refunds when `amount` is provided (e.g. post-release dispute clawback).
    Returns {'ok', 'error', 'unconfirmed', 'text'}:
      ok=False                    -> the call failed (HTTP error, or the answer itself reports a failure)
      ok=True, unconfirmed=True   -> HTTP 200 but no refund id / status came back, so NOTHING is recorded
      ok=True, unconfirmed=False  -> a refund id / status came back and was saved
    """
    payload = {
        'request_id': request_id,
        'reason': REFUND_REASON,
        'is_dispute_refund': bool(is_dispute_refund),
    }
    if amount is not None:
        try:
            amt = float(amount)
            if amt > 0:
                payload['amount'] = round(amt, 2)
        except (TypeError, ValueError):
            pass

    try:
        resp = _post_function('xendit-refund', payload)
    except Exception as e:
        return {'ok': False, 'unconfirmed': False, 'text': '',
                'error': f'{e} | Likely cause: {_refund_error_hint(e)}'}

    text = (resp.text or '').strip()[:300]
    try:
        body = resp.json()
    except ValueError:
        body = None

    # A 200 can still carry an error
    if isinstance(body, dict) and (body.get('error') or body.get('success') is False or body.get('ok') is False):
        msg = body.get('error') or body.get('message') or text
        return {'ok': False, 'unconfirmed': False, 'text': text,
                'error': f'xendit-refund answered HTTP {resp.status_code} but reported a failure: {msg} '
                         f'| Likely cause: {_refund_error_hint(msg)}'}

    rid, st = _extract_refund_fields(body)
    if st and st.upper() in REFUND_FAILED_STATUSES:
        _save_refund_result(request_id, rid, st)
        return {'ok': False, 'unconfirmed': False, 'text': text,
                'error': f'Xendit returned the refund with status {st.upper()}. Response: {text}'}
    if rid or st:
        _save_refund_result(request_id, rid, st)
        return {'ok': True, 'unconfirmed': False, 'text': text, 'refund_id': rid, 'refund_status': st}
    return {'ok': True, 'unconfirmed': True, 'text': text}


def _manual_refund_allowed():
    """Manual "mark as paid" is only for sandbox / demo. On in DEBUG; override with ALLOW_MANUAL_REFUND_MARK."""
    return bool(getattr(settings, 'ALLOW_MANUAL_REFUND_MARK', getattr(settings, 'DEBUG', False)))


def _suggest_strike(sub_issue, category):
    """(default reason category, tick the strike box by default?) for a reported issue."""
    text = f'{sub_issue or ""} {category or ""}'.lower()
    if any(k in text for k in ('lost', 'damag', 'wrong item', 'not received', 'missing')):
        return 'Lost or damaged cargo', True
    if any(k in text for k in ('fraud', 'fake', 'falsif')):
        return 'Fraud or falsified proof of delivery', False
    if any(k in text for k in ('delay', 'late', 'no-show', 'no show', 'show up', 'responding')):
        return 'Late or no-show', False
    return 'Other', False


def _recommend(r):
    """
    Evidence-based suggestion for the admin (the admin still makes the call).
    Uses what the system already recorded: pickup / drop-off QR, POD photo, arrival timestamp,
    failed-delivery proof and the return-to-sender confirmation.
    lean: 'sender' (courier at fault -> refund + strike), 'courier' (courier not at fault), 'review'.
    """
    sub_issue = (r['sub_issue'] or '').lower()
    category = (r['category'] or '').lower()
    is_damage = 'damag' in sub_issue
    is_wrong = 'wrong' in sub_issue or 'missing' in sub_issue
    is_late = any(k in sub_issue for k in ('later than', 'delayed', 'stopped responding'))
    picked = bool(r['pickup_verified'])
    delivered = bool(r['dropoff_verified'])
    pod = bool(r['pod_photo_url'])
    failed = bool(r['failure_reason'])
    returned = bool(r['return_verified'])
    arrived = bool(r['dropoff_arrived_at'])

    def out(lean, headline, detail, category=None, severe_hint=False):
        return {'lean': lean, 'headline': headline, 'detail': detail,
                'category': category, 'severe_hint': severe_hint}

    if 'behavior' in category:
        return out('review', 'Conduct report: decide from the statements',
                   'This is about how the courier behaved, so the delivery evidence does not settle it. Read both '
                   'sides. A strike fits serious or repeated misconduct (unsafe driving, asking for extra payment).',
                   'Other')
    if is_late:
        return out('review', 'Timing report: compare the promised time with what happened',
                   'Check the scheduled time / ETA against the actual pickup and drop-off. A strike fits extreme or '
                   'repeated lateness; a refund fits when the delay made the delivery pointless.',
                   'Late or no-show')
    if not r['has_qr']:
        return out('review', 'Not enough system evidence',
                   'There is no pickup / drop-off QR record for this delivery. Decide from the statements and photos.')
    if not picked:
        return out('sender', 'Courier never collected the parcel',
                   'The pickup QR was never verified, so the parcel never left the sender. Nothing was lost: the '
                   'courier did not show up. Refund the sender in full and add a strike.',
                   'Late or no-show')
    if failed:
        if returned:
            return out('courier', 'Failed delivery proven and parcel returned',
                       'The courier recorded a failed-delivery proof and the parcel was confirmed back with the '
                       'sender. The courier followed the process, so a strike is not suggested.')
        return out('review', 'Failed delivery reported, return not confirmed',
                   'The courier reported a failed delivery, but the return to the sender is not confirmed yet. '
                   'Make sure the parcel gets back to the sender before ruling.')
    if delivered and pod:
        if is_damage or is_wrong:
            return out('review', 'Delivered with proof: check what the receiver actually got',
                       'Drop-off was verified with a POD photo. Compare the POD photo with the sender\'s photos. '
                       'Damage or a wrong item that is visible at hand-over points to the courier; packaging that '
                       'was already weak at pickup does not.', 'Lost or damaged cargo')
        return out('courier', 'Delivery verified with proof',
                   'The drop-off QR was verified and a POD photo exists. Check the arrival time and location '
                   'before dismissing a "not received" claim.')
    if delivered and not pod:
        return out('review', 'Drop-off verified but no POD photo',
                   'The receiver used the drop-off QR/PIN, but the courier uploaded no proof photo. Ask the '
                   'courier for proof before ruling.')
    # picked up, never delivered, no failed-delivery proof, no return
    detail = ('The parcel was collected, but there is no drop-off verification, no POD photo, no failed-delivery '
              'proof and no return. The parcel is unaccounted for. Refund the sender and add a strike.')
    if not arrived:
        detail += ' No arrival at the drop-off was recorded either.'
    return out('sender', 'Parcel collected but never delivered', detail,
               'Lost or damaged cargo', severe_hint=True)


def _strike_map(provider_ids):
    """
    {provider_id: {'points', 'tickets', 'deliveries'}} for ACTIVE strikes.
    Returns None when the strike tables are missing, so the page still loads without them.
    """
    ids = sorted({int(i) for i in provider_ids if i})
    if not ids:
        return {}
    out = {}
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT provider_id, weight, ticket_id, delivery_id FROM provider_strikes "
                    "WHERE status = 'active' AND provider_id = ANY(%s)",
                    [ids],
                )
                for pid, weight, tid, did in cur.fetchall():
                    info = out.setdefault(pid, {'points': 0, 'tickets': set(), 'deliveries': set()})
                    info['points'] += int(weight or 0)
                    if tid:
                        info['tickets'].add(tid)
                    if did:
                        info['deliveries'].add(did)
    except Exception as e:
        print(f'[disputes] strike lookup skipped: {e}')
        return None
    return out


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
                st.reporter_role,
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
                'sender'::text AS reporter_role,
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
            uq.reporter_id, uq.reporter_role,

            dr.estimated_cost, dr.base_fare, dr.return_deposit,
            dr.fallback_action, dr.fallback_recipient_name,
            dr.escrow_status AS req_escrow_status, dr.payment_provider,
            dr.refund_id, dr.refund_status, dr.refund_requested_at, dr.escrow_refunded_at,
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
            (SELECT pw.balance FROM provider_wallet pw WHERE pw.provider_id = d.provider_id) AS provider_balance,
            (SELECT tr.base_amount FROM transactions tr WHERE tr.escrow_id = ep.escrow_id LIMIT 1) AS payout_base,

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


def _build(r, strikes=None):
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

    # ---- Payout already released? (damaged / wrong item / not received reported after delivery) ----
    can_post_release = bool(
        ticket_open and del_id and req_id and state == 'released' and r['provider_id'] and r['escrow_id']
    )
    max_claw = float(r['ep_amount'] or 0)
    default_claw = float(r['payout_base'] if r['payout_base'] is not None else max_claw)
    post_release = {
        'can': can_post_release,
        'default': min(default_claw, max_claw),
        'max': max_claw,
        'balance': float(r['provider_balance']) if r['provider_balance'] is not None else None,
    }

    # ---- Refund tracking: escrow ledger says "refunded", but did the MONEY actually go back? ----
    refund_raw = (r['refund_status'] or '').strip()
    refund_up = refund_raw.upper()
    if state != 'refunded':
        refund_state, refund_label = 'none', ''
    elif refund_up in REFUND_OK_STATUSES:
        refund_state, refund_label = 'succeeded', 'Refund paid'
    elif refund_up in REFUND_FAILED_STATUSES:
        refund_state, refund_label = 'failed', 'Refund failed'
    elif refund_up in REFUND_PENDING_STATUSES or r['refund_id']:
        refund_state, refund_label = 'pending', 'Refund pending'
    else:
        refund_state, refund_label = 'not_requested', 'Refund not sent'
    can_retry_refund = bool(req_id and refund_state in ('failed', 'not_requested'))

    # ---- Provider strike standing (for the merged "also issue a strike" option) ----
    pid = r['provider_id']
    sinfo = (strikes or {}).get(pid) or {'points': 0, 'tickets': set(), 'deliveries': set()}
    pts = int(sinfo['points'])
    reporter_is_provider = bool(pid and (r['reporter_role'] == 'provider' or r['reporter_id'] == pid))
    already_struck = bool(
        (ticket_id and ticket_id in sinfo['tickets'])
        or (not ticket_id and del_id and del_id in sinfo['deliveries'])
    )
    suggested_category, default_on = _suggest_strike(r['sub_issue'], r['category'])
    reco = _recommend(r)
    if reco['lean'] == 'sender':
        default_on = True
    elif reco['lean'] == 'courier':
        default_on = False
    if reco['category']:
        suggested_category = reco['category']
    strike = {
        'available': strikes is not None,
        'can': bool(ticket_open and pid and not reporter_is_provider),
        'points': min(pts, REMOVAL_POINTS),
        'next': consequence_for(pts + 1),
        'at_limit': pts >= REMOVAL_POINTS,
        'already': already_struck,
        'category': suggested_category,
        'default_on': default_on,
        'severe_hint': reco['severe_hint'],
    }

    display_ref = (
        r['case_ref']
        or (f"Ticket #{ticket_id}" if ticket_id else f"Case #{dispute_id}")
    )

    provider_name = _name(
        r['provider_name'],
        f"USR-{r['provider_id']}" if r['provider_id'] else 'No courier assigned',
    )
    meta = {
        'unified_id': unified_id,
        'case_ref': display_ref,
        'provider_name': provider_name,
        'state': state,
        'total_held': _money(est),
        'strike': strike,
        'refund': {'state': refund_state, 'label': refund_label, 'can_retry': can_retry_refund,
                   'manual_allowed': _manual_refund_allowed()},
        'post_release': post_release,
    }

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
        'payment_provider_raw': r['payment_provider'] or '',

        'state': state,
        'state_label': state_label,
        'group': group,
        'is_open': ticket_open,
        'can_act': can_settle_escrow,
        'can_note_resolve': ticket_open,

        'refund_state': refund_state,
        'refund_label': refund_label,
        'refund_status_raw': refund_raw,
        'refund_id': r['refund_id'] or '',
        'refund_requested_at': fmt_manila(r['refund_requested_at']),
        'can_retry_refund': can_retry_refund,
        'can_post_release_refund': can_post_release,
        'post_release': post_release,
        'reco': reco,
        'strike': strike,
        'meta_id': f'meta-{unified_id}',
        'meta': meta,

        'total_held': _money(est),
        'base_fare': _money(base),
        'return_deposit': _money(deposit),
        'fallback': fallback,
        'fallback_name': fallback_name,

        'sender_name': _name(r['sender_name'], f"USR-{r['sender_id']}" if r['sender_id'] else 'Unknown sender'),
        'sender_phone': r['sender_phone'] or '\u2014',
        'sender_email': r['sender_email'] or '\u2014',
        'provider_name': provider_name,
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
def _build_all(rows):
    """Build every case with one bulk strike lookup (None map = strike tables unavailable)."""
    strikes = _strike_map([r['provider_id'] for r in rows])
    return [_build(r, strikes) for r in rows]


@admin_required
def admin_disputes_view(request):
    current_tab = request.GET.get('tab', 'open')
    if current_tab not in ('open', 'frozen', 'refund', 'resolved', 'dismissed', 'all'):
        current_tab = 'open'
    initial_q = (request.GET.get('q') or request.GET.get('delivery_id') or '').strip()

    all_tickets, error = [], None
    try:
        all_tickets = _build_all(_load_unified_disputes())
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
        'refund': sum(1 for t in all_tickets if t['can_retry_refund']),
    }

    if current_tab == 'all':
        tickets = all_tickets
    elif current_tab == 'open':
        tickets = [t for t in all_tickets if t['is_open']]
    elif current_tab == 'refund':
        tickets = [t for t in all_tickets if t['can_retry_refund']]
    else:
        tickets = [t for t in all_tickets if t['group'] == current_tab]

    return render(request, 'pages/admin_disputes.html', {
        'current_tab': current_tab,
        'tickets': tickets,
        'counts': counts,
        'error': error,
        'initial_q': initial_q,
        'strike_config': {
            'categories': list(REASON_CATEGORIES),
            'days': list(SUSPENSION_DAY_OPTIONS),
            'default_days': DEFAULT_SUSPENSION_DAYS,
            'removal_points': REMOVAL_POINTS,
        },
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


def _clawback_release(cur, t, claw):
    """
    Payout was already released to the courier. Mark the escrow refunded and recover `claw` from the courier's
    wallet. Runs inside the verdict transaction: if anything here fails, nothing is saved.
    The wallet is allowed to go negative: the courier cannot cash out until future earnings cover the debt.
    """
    cur.execute("SELECT escrow_status FROM escrow_payments WHERE escrow_id = %s FOR UPDATE", [t['escrow_id']])
    row = cur.fetchone()
    if not row or str(row[0] or '').strip().lower() not in ('released', 'completed'):
        raise DisputeError('The escrow is no longer in the released state. Reload the page and try again.', 409)

    cur.execute(
        "SELECT wallet_id FROM provider_wallet WHERE provider_id = %s FOR UPDATE", [t['provider_id']]
    )
    wallet = cur.fetchone()
    if not wallet and claw > 0:
        raise DisputeError("The courier has no wallet to recover from. Set the amount to 0 or use 'Resolve with Note'.", 409)
    if wallet and claw > 0:
        cur.execute(
            "UPDATE provider_wallet SET balance = balance - %s, updated_at = NOW() WHERE wallet_id = %s",
            [claw, wallet[0]],
        )

    cur.execute("UPDATE escrow_payments SET escrow_status = 'Refunded' WHERE escrow_id = %s", [t['escrow_id']])
    cur.execute(
        "UPDATE delivery_requests SET escrow_status = 'refunded', escrow_refunded_at = NOW() WHERE request_id = %s",
        [t['request_id']],
    )
    provider = (t.get('payment_provider_raw') or '').strip().lower()
    if provider in ('gcash', 'maya'):
        cur.execute(
            """
            INSERT INTO escrow_transactions (request_id, event, amount, provider, notes)
            VALUES (%s, 'dispute_refund_after_release', %s, %s, %s)
            """,
            [t['request_id'], float(claw), provider,
             f"Refund after release. Recovered {claw} from courier wallet. Case {t['case_ref']}."],
        )


def _cancel_in_flight_delivery(cur, t):
    """
    The sender was refunded, so a delivery that is still unfinished must not stay "In Transit" or "Accepted"
    (the sender's Activity and the provider's job list read delivery_requests.delivery_status).
    Finished deliveries (Completed / Returned / Returning / already Cancelled) are left alone.
    Returns True when the status was changed.
    """
    if not t['request_id']:
        return False
    cur.execute(
        """
        UPDATE delivery_requests
           SET delivery_status = 'Cancelled'
         WHERE request_id = %s
           AND delivery_status IN ('Pending', 'Accepted', 'In Transit', 'Awaiting Approval')
        """,
        [t['request_id']],
    )
    changed = bool(cur.rowcount and cur.rowcount > 0)
    if changed and t['delivery_id']:
        cur.execute(
            "INSERT INTO delivery_status_history (delivery_id, status) VALUES (%s, 'Cancelled')",
            [t['delivery_id']],
        )
    return changed


def _lock_open_case(cur, t):
    """Lock the case row and re-check it is still open (stops double-click / two-admin races)."""
    if t['ticket_id']:
        cur.execute("SELECT status FROM support_tickets WHERE ticket_id = %s FOR UPDATE", [t['ticket_id']])
        row = cur.fetchone()
        if row and row[0] in ('Resolved', 'Closed'):
            raise DisputeError('This dispute case is already closed.', 409)
    elif t['dispute_id']:
        cur.execute("SELECT status FROM disputes WHERE dispute_id = %s FOR UPDATE", [t['dispute_id']])
        row = cur.fetchone()
        if row and row[0] in ('Resolved', 'Dismissed'):
            raise DisputeError('This dispute case is already closed.', 409)


def _plan_strike(t, req, note, warnings):
    """
    Validate the optional strike BEFORE any money moves.
    Returns a plan dict, or None when the strike is skipped (a warning is added).
    Raises StrikeError for input the admin must fix.
    """
    s = t['strike']
    if not s['available']:
        raise StrikeError('The strike tables are not available. Run provider_strikes.sql first, or untick the strike option.')
    if not t['provider_id'] or not s['can']:
        raise StrikeError('A strike can only be issued to the courier on a sender report.')
    if s['at_limit']:
        warnings.append('The courier is already at the strike limit, so no new strike was added.')
        return None
    if s['already']:
        warnings.append('A strike was already issued for this case, so no second strike was added.')
        return None

    category = (req.get('reason_category') or '').strip()
    if category not in REASON_CATEGORIES:
        raise StrikeError('Choose a reason category for the strike.')
    try:
        days = int(req.get('suspension_days') or DEFAULT_SUSPENSION_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_SUSPENSION_DAYS
    if days not in SUSPENSION_DAY_OPTIONS:
        days = DEFAULT_SUSPENSION_DAYS

    base = f"Dispute {t['case_ref']} ({t['sub_issue']}) was ruled against you."
    reason = (req.get('reason') or '').strip() or (f'{base} {note}' if note else base)
    if len(reason) < 10:
        reason = base
    return {'category': category, 'reason': reason, 'severe': bool(req.get('severe')), 'days': days}


def _strike_message(request, t, plan, result, warnings):
    """Post-commit side effects of a strike. Returns the text appended to the success message."""
    try:
        _log_strike(request, t['provider_id'], result, plan['category'])
    except Exception as e:
        print(f'[disputes] strike log failed: {e}')
    if result.get('active_deliveries', 0) > 0:
        warnings.append(
            f"The courier still has {result['active_deliveries']} delivery(ies) in progress. "
            'Make sure they get completed or reassigned.'
        )
    return (f" Strike issued \u2014 courier is now at {result['points']}/{REMOVAL_POINTS} "
            f"({result['consequence']}).")


def _record_refund_failure(request, t, err):
    """Make a failed Xendit call visible (admin log + case timeline) instead of silently 'Refunded'."""
    try:
        log_admin_action(
            request,
            f"Xendit refund FAILED for {t['case_ref']} ({t['request_label']}): {str(err).split(' | Likely cause:')[0][:120]}. "
            'Retry it from the Disputes page.',
        )
    except Exception as e:
        print(f'[disputes] log_admin_action failed: {e}')
    if t['ticket_id']:
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO ticket_events (ticket_id, status, note) VALUES (%s, 'Resolved', %s)",
                    [t['ticket_id'], 'Refund is being processed by Pack-N-Ship support.'],
                )
        except Exception as e:
            print(f'[disputes] refund event insert failed: {e}')


def _push(uid, title, body, data):
    if not uid:
        return
    try:
        _post_function('send-push', {'user_id': uid, 'title': title, 'body': body, 'data': data}, timeout=8)
    except Exception as e:
        print(f'[disputes] push to user {uid} skipped: {e}')


def _mark_refund_manually(request, t, note):
    """
    Sandbox / demo escape hatch: record that the sender WAS refunded although the Xendit call is unavailable.
    This sends NO money. It only sets delivery_requests.refund_status = 'SUCCEEDED' (which also fires the
    "Refund completed" notification to the sender) and leaves a clear admin-log entry.
    """
    if not _manual_refund_allowed():
        return JsonResponse({'error': 'Manual refund marking is disabled on this server.'}, status=403)
    if not t['can_retry_refund']:
        return JsonResponse({'error': 'Nothing to mark: the refund is already paid, or still pending with Xendit.'}, status=409)
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_requests
                       SET refund_status = 'SUCCEEDED',
                           refund_requested_at = COALESCE(refund_requested_at, NOW()),
                           escrow_refunded_at = COALESCE(escrow_refunded_at, NOW())
                     WHERE request_id = %s
                    """,
                    [t['request_id']],
                )
                if t['ticket_id']:
                    cur.execute(
                        "INSERT INTO ticket_events (ticket_id, status, note) VALUES (%s, 'Resolved', %s)",
                        [t['ticket_id'], 'Refund confirmed by Pack-N-Ship support.'],
                    )
    except Exception as e:
        return JsonResponse({'error': f'Nothing was changed. {e}'}, status=500)
    try:
        log_admin_action(
            request,
            f"MANUALLY marked refund as paid for {t['case_ref']} ({t['request_label']}), {t['total_held']}: "
            f"no Xendit call was made. {note[:80]}".strip(),
        )
    except Exception as e:
        print(f'[disputes] log_admin_action failed: {e}')
    return JsonResponse({'status': 'success', 'message': 'Refund marked as paid (manual). No money was sent by the system.', 'warnings': []})


def _retry_refund(request, t):
    """Re-send the refund to Xendit for a case whose escrow is 'Refunded' but whose money never went back."""
    if not t['can_retry_refund']:
        return JsonResponse({
            'error': 'Nothing to retry: the refund is already paid, or Xendit is still processing it.'
        }, status=409)

    # Check if this was a post-release partial dispute refund so we retry with the exact amount
    retry_amount = None
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT amount FROM escrow_transactions
                 WHERE request_id = %s AND event = 'dispute_refund_after_release'
                 ORDER BY created_at DESC LIMIT 1
                """,
                [t['request_id']],
            )
            row = cur.fetchone()
            if row and row[0] is not None and float(row[0]) > 0:
                retry_amount = float(row[0])
    except Exception:
        pass

    call = _xendit_refund_call(t['request_id'], amount=retry_amount, is_dispute_refund=True)
    if not call['ok']:
        _record_refund_failure(request, t, call['error'])
        return JsonResponse({'error': f"The refund request failed again: {call['error']} Nothing was changed."}, status=502)
    if call['unconfirmed']:
        return JsonResponse({
            'error': ('xendit-refund answered OK, but it returned no refund id or status, so NO refund was recorded. '
                      f"Its response: {call['text'] or '(empty)'} | Check Edge Functions > xendit-refund > Logs in "
                      'Supabase, and make sure the function writes refund_id / refund_status on delivery_requests.')
        }, status=409)

    try:
        log_admin_action(request, f"Retried Xendit refund for {t['case_ref']} ({t['request_label']}), {t['total_held']}")
    except Exception as e:
        print(f'[disputes] log_admin_action failed: {e}')

    ref = t['request_label'].lstrip('#')
    _push(t['sender_id'], 'Refund requested',
          f'The refund for parcel #{ref} has been sent for processing. We will notify you once it is completed.',
          {'type': 'dispute_resolved', 'requestId': t['request_id'], 'ticketId': t['ticket_id'], 'role': 'sender'})
    return JsonResponse({
        'status': 'success',
        'message': f"Refund request sent to Xendit (status: {call.get('refund_status') or 'requested'}).",
        'warnings': [],
    })


@admin_required
@require_POST
def resolve_dispute(request, ticket_id):
    """
    Handles every dispute outcome:
      - 'courier'      : unfreeze & release escrow to the courier + mark Resolved
      - 'sender'       : refund escrow to the sender + Xendit refund + mark Resolved
                         (+ optional provider strike, same transaction)
      - 'sender_released': payout was ALREADY released: refund the sender through Xendit and recover the
                         amount from the courier's wallet, in one transaction (+ optional strike)
      - 'resolve'      : mark Resolved with an admin note (+ optional provider strike)
      - 'dismiss'      : mark Dismissed/Closed with an admin reason
      - 'retry_refund' : re-send a failed / missing Xendit refund (works on closed cases)
      - 'mark_refunded': sandbox/demo only (DEBUG or ALLOW_MANUAL_REFUND_MARK): record the refund as paid by hand
    """
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    outcome = (payload.get('outcome') or '').strip().lower()
    custom_note = (payload.get('resolution') or payload.get('note') or '').strip()
    strike_req = payload.get('strike') or {}

    if outcome not in ('courier', 'sender', 'sender_released', 'resolve', 'dismiss', 'retry_refund', 'mark_refunded'):
        return JsonResponse({'error': 'Unknown resolution outcome.'}, status=400)

    try:
        case_id = int(ticket_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid case id.'}, status=400)
    if case_id == 0:
        # Id 0 would make the loader return EVERY case and we would act on the wrong one.
        return JsonResponse({'error': 'Invalid case id. Reload the page and try again.'}, status=400)

    try:
        rows = _load_unified_disputes(ticket_id=case_id)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    if not rows:
        return JsonResponse({'error': 'Dispute case not found.'}, status=404)

    t = _build_all(rows)[0]
    if t['unified_id'] != case_id:
        return JsonResponse({'error': 'The case did not match the request. Reload the page and try again.'}, status=409)

    if outcome == 'retry_refund':
        return _retry_refund(request, t)
    if outcome == 'mark_refunded':
        return _mark_refund_manually(request, t, custom_note)

    if not t['is_open']:
        return JsonResponse({'error': 'This dispute case is already closed.'}, status=409)

    warnings = []
    tx_hash = ''

    # Validate the optional strike first, so a bad form never fails AFTER money has moved.
    strike_plan = None
    if outcome in ('sender', 'sender_released', 'resolve') and strike_req.get('issue'):
        try:
            strike_plan = _plan_strike(t, strike_req, custom_note, warnings)
        except StrikeError as e:
            return JsonResponse({'error': e.message}, status=e.status)

    # =========================================================================
    # A) ESCROW VERDICTS ('courier' or 'sender' or 'sender_released')
    # =========================================================================
    if outcome in ('courier', 'sender', 'sender_released'):
        if outcome == 'sender_released':
            if not t['can_post_release_refund']:
                return JsonResponse({
                    'error': 'This option is only for cases whose escrow was already released to the courier.'
                }, status=409)
        elif not t['can_act']:
            return JsonResponse({
                'error': 'Escrow settlement is not available for this case (missing delivery or escrow already settled).'
            }, status=409)

        claw = Decimal('0')
        if outcome == 'sender_released':
            try:
                claw = Decimal(str(payload.get('clawback_amount', t['post_release']['default'])))
            except (InvalidOperation, TypeError, ValueError):
                return JsonResponse({'error': 'Enter a valid amount to recover from the courier.'}, status=400)
            if claw < 0 or claw > Decimal(str(t['post_release']['max'])):
                return JsonResponse({
                    'error': f"The amount to recover must be between {_money(0)} and {_money(t['post_release']['max'])}."
                }, status=400)

        if outcome == 'courier':
            rpc_outcome = 'resolve_dispute_release'
            default_res = 'Ruled in favor of the courier. Escrow unfrozen and released to the provider wallet.'
            message = 'Escrow unfrozen and released to the Provider wallet.'
            log_verdict = 'in favor of the Courier (escrow released)'
        elif outcome == 'sender':
            rpc_outcome = 'resolve_dispute_refund'
            default_res = 'Ruled in favor of the sender. Escrow refunded; payout withheld from the courier.'
            message = 'Sender refunded and dispute marked Resolved.'
            log_verdict = 'in favor of the Sender (escrow refunded)'
        else:
            rpc_outcome = None
            default_res = (f"Ruled in favor of the sender. The payout had already been released, so the sender is "
                           f"refunded {_money(claw)} and the amount is recovered from the courier's wallet.")
            message = f'Sender refunded {_money(claw)}; {_money(claw)} recovered from the courier wallet.'
            log_verdict = f'in favor of the Sender (refund after release, {_money(claw)} recovered from courier)'
        resolution = f'{default_res} Note: {custom_note}' if custom_note else default_res

        strike_result = None
        delivery_cancelled = False
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    _lock_open_case(cur, t)
                    if outcome == 'sender_released':
                        _clawback_release(cur, t, claw)
                    else:
                        cur.execute(
                            "SELECT public.settle_delivery_escrow(p_delivery_id => %s, p_outcome => %s)",
                            [t['delivery_id'], rpc_outcome],
                        )
                    if outcome in ('sender', 'sender_released'):
                        delivery_cancelled = _cancel_in_flight_delivery(cur, t)
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

                    # Provider strike: same transaction as the refund. If it fails, NOTHING is saved.
                    if strike_plan:
                        strike_result = _issue_strike_tx(
                            cur, _issuer_id(request), t['provider_id'],
                            strike_plan['category'], strike_plan['reason'],
                            strike_plan['severe'], strike_plan['days'],
                            t['ticket_id'], t['delivery_id'],
                        )

                    _notify_parties_in_db(
                        cur,
                        t['sender_id'],
                        t['provider_id'],
                        f"Dispute {t['case_ref']} resolved",
                        resolution,
                        t['dispute_id'] or t['ticket_id'],
                    )
        except StrikeError as e:
            return JsonResponse({'error': f'Nothing was changed. {e.message}'}, status=e.status)
        except Exception as e:
            return JsonResponse({'error': f'Nothing was changed. {e}'}, status=400)

        if delivery_cancelled:
            message += ' The unfinished delivery was marked Cancelled.'
        if strike_result:
            message += _strike_message(request, t, strike_plan, strike_result, warnings)

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

        # Live Xendit refund on sender verdict (passes partial amount for sender_released).
        refund_error = None
        if outcome in ('sender', 'sender_released') and t['request_id']:
            refund_amt = float(claw) if (outcome == 'sender_released' and claw > 0) else None
            call = _xendit_refund_call(t['request_id'], amount=refund_amt, is_dispute_refund=True)
            if not call['ok']:
                refund_error = call['error']
                _record_refund_failure(request, t, refund_error)
                warnings.append(
                    f'The ledger is marked Refunded, but the Xendit refund call failed ({refund_error}). '
                    'The sender has NOT been paid yet. Open Disputes > Refund Issues and press '
                    '"Retry Xendit Refund".'
                )
            elif call['unconfirmed']:
                warnings.append(
                    'xendit-refund answered OK but returned no refund id or status, so the refund is not recorded '
                    f"yet. If this case stays on \"Refund not sent\", check the xendit-refund logs. "
                    f"Response: {call['text'] or '(empty)'}"
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
            if outcome == 'sender_released' and claw > 0:
                sender_body = (
                    f'Your dispute for parcel #{ref} was upheld. A refund of {_money(claw)} has been requested. We will notify you again once it is completed.'
                    if not refund_error else
                    f'Your dispute for parcel #{ref} was upheld. Your refund of {_money(claw)} is being processed by our team.'
                )
            else:
                sender_body = (
                    f'Your dispute for parcel #{ref} was upheld. A full refund has been requested. We will notify you again once it is completed.'
                    if not refund_error else
                    f'Your dispute for parcel #{ref} was upheld. Your refund is being processed by our team.'
                )
            provider_body = f"The dispute for parcel #{ref} was resolved in the sender's favor. No payout will be released."
            if outcome == 'sender_released':
                provider_body = (f"The dispute for parcel #{ref} was resolved in the sender's favor. "
                                 f"{_money(claw)} was deducted from your wallet.")
            if strike_result:
                provider_body += ' A strike was added to your account. Open Account Health for details.'
            msgs = [
                (t['sender_id'], 'Dispute resolved in your favor', sender_body, 'sender'),
                (t['provider_id'], 'Dispute resolved', provider_body, 'provider'),
            ]
        for uid, p_title, p_body, role in msgs:
            _push(uid, p_title, p_body, {**push_data, 'role': role})

        return JsonResponse({
            'status': 'success',
            'message': message,
            'warnings': warnings,
            'refund_failed': bool(refund_error),
            'strike': ({k: strike_result[k] for k in ('consequence', 'points', 'suspended_until')}
                       if strike_result else None),
        })

    # =========================================================================
    # B) GENERAL RESOLVE / DISMISS WITH NOTE ('resolve' or 'dismiss')
    # =========================================================================
    if len(custom_note) < 5:
        return JsonResponse({'error': 'Please provide a resolution/dismissal note (at least 5 characters).'}, status=400)

    is_dismiss = (outcome == 'dismiss')
    new_dispute_status = 'Dismissed' if is_dismiss else 'Resolved'
    new_ticket_status = 'Closed' if is_dismiss else 'Resolved'
    action_word = 'Dismissed' if is_dismiss else 'Resolved'

    strike_result = None
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                _lock_open_case(cur, t)
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

                if strike_plan:
                    strike_result = _issue_strike_tx(
                        cur, _issuer_id(request), t['provider_id'],
                        strike_plan['category'], strike_plan['reason'],
                        strike_plan['severe'], strike_plan['days'],
                        t['ticket_id'], t['delivery_id'],
                    )

                _notify_parties_in_db(
                    cur,
                    t['sender_id'],
                    t['provider_id'],
                    f"Dispute {t['case_ref']} {action_word.lower()}",
                    custom_note,
                    t['dispute_id'] or t['ticket_id'],
                )
    except StrikeError as e:
        return JsonResponse({'error': f'Nothing was changed. {e.message}'}, status=e.status)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    message = f"Case {t['case_ref']} marked as {new_dispute_status}."
    if strike_result:
        message += _strike_message(request, t, strike_plan, strike_result, warnings)

    log_admin_action(request, f"{action_word} Dispute {t['case_ref']} ({t['request_label']}): {custom_note[:80]}")

    return JsonResponse({
        'status': 'success',
        'new_status': new_dispute_status,
        'message': message,
        'warnings': warnings,
        'strike': ({k: strike_result[k] for k in ('consequence', 'points', 'suspended_until')}
                   if strike_result else None),
    })


# ---------------------------------------------------------------------------
# Legacy JSON API endpoints (preserved so existing API routes remain valid)
# ---------------------------------------------------------------------------
@admin_required
@require_http_methods(["GET"])
def disputes_list_api(request):
    tab = request.GET.get('tab', 'open')
    search = (request.GET.get('q') or '').strip().lower()
    items = _build_all(_load_unified_disputes())

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
    return JsonResponse({'dispute': _build_all(rows[0:1])[0]})


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
