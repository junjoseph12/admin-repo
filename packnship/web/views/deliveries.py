# views/deliveries.py
import json
import os

from django.shortcuts import render, redirect
from django.db import connection
from django.http import Http404
from django.urls import reverse
from .login import admin_required
from ..supabase_storage import StorageError, create_signed_url, parse_storage_ref

TS_FMT = '%b %d, %Y — %I:%M %p'

# Photo kinds -> fixed SQL (nothing from the request is ever interpolated). Looked up by request_id.
DELIVERY_PHOTO_QUERIES = {
    'cargo':   "SELECT cp.cargo_pic FROM delivery_requests dr JOIN cargo_profiles cp ON cp.cargo_id = dr.cargo_id WHERE dr.request_id = %s",
    'pickup':  "SELECT d.pickup_photo_url FROM deliveries d WHERE d.request_id = %s",
    'pod':     "SELECT d.pod_photo_url FROM deliveries d WHERE d.request_id = %s",
    'failure': "SELECT d.failure_photo_url FROM deliveries d WHERE d.request_id = %s",
    'return':  "SELECT d.return_pod_photo_url FROM deliveries d WHERE d.request_id = %s",
}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _ts(value):
    return value.strftime(TS_FMT) if value else ''


def _money(value):
    """Money as a plain '1234.50' string, so Django's localisation never turns it into '1,234.5'."""
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _num(value):
    return float(value) if value is not None else 0.0


def _coord(value):
    return str(float(value)) if value is not None else ''


def _media_url(request_id, kind, stored):
    """Admin-only URL for a delivery photo, or '' when nothing real is stored."""
    if not stored or str(stored).strip().upper() in ('', 'N/A'):
        return ''
    return reverse('delivery_photo', args=[request_id, kind])


def _normalize_escrow_status(raw):
    """Map DB values to a canonical display status."""
    s = (raw or '').strip().lower().replace('_', ' ')
    if s in ('released', 'completed'):
        return 'Released'
    if s == 'refunded':
        return 'Refunded'
    if s == 'frozen':
        return 'Frozen'
    if s in ('on hold', 'onhold', 'pending', 'held', ''):
        return 'On Hold'
    if s in ('cancelled', 'canceled'):
        return 'Cancelled'
    return (raw or 'On Hold').title()


def _normalize_delivery_status(delivery_status, latest_status, completed_at, pickup_verified,
                               dropoff_verified, return_verified, returned_at, failed_at,
                               failure_reason, del_id):
    """Normalize status from delivery_requests, delivery_status_history, deliveries and qr_verifications."""
    raw_req = (delivery_status or '').strip().lower().replace('_', ' ').replace('-', ' ')
    raw_hist = (latest_status or '').strip().lower().replace('_', ' ').replace('-', ' ')

    # 1. Cancelled takes top priority
    if 'cancel' in raw_req or 'cancel' in raw_hist:
        return 'Cancelled'

    # 2. Completed / Delivered
    if (
        completed_at
        or dropoff_verified
        or raw_req in ('completed', 'delivered')
        or 'delivered' in raw_hist
        or 'completed' in raw_hist
    ):
        return 'Completed'

    # 3. Returned to sender (failed handoff that came back)
    if returned_at or return_verified or 'return' in raw_req or 'return' in raw_hist:
        return 'Returned'

    # 4. Failed handoff (receiver unreachable, wrong address, ...)
    if failed_at or failure_reason or 'fail' in raw_req or 'fail' in raw_hist:
        return 'Failed'

    # 5. In Transit (explicitly in transit, picked up, or QR pickup verified)
    in_transit_keywords = (
        'in transit', 'intransit', 'picked up', 'pickup verified',
        'on the way', 'en route', 'out for delivery', 'departed', 'moving'
    )
    if (
        pickup_verified
        or any(k in raw_hist for k in in_transit_keywords)
        or any(k in raw_req for k in in_transit_keywords)
    ):
        return 'In Transit'

    # 6. Accepted / Assigned
    if del_id or raw_req in ('accepted', 'assigned', 'in progress', 'active') or 'accept' in raw_hist:
        return 'Accepted'

    # 7. Default to Pending
    return 'Pending'


def _build_timeline_events(r, db_history, normalized_status):
    """
    Build a complete, chronological list of timeline events:
      [{'status': '...', 'time': '...', 'verified': bool}, ...]
    Combines delivery_requests / deliveries milestone timestamps with delivery_status_history rows
    so the timeline is never blank when a delivery has occurred.
    """
    events = []
    seen_labels = set()

    def add_event(label, dt_val, verified=False):
        norm_key = label.strip().lower()
        if norm_key in seen_labels:
            return
        seen_labels.add(norm_key)
        events.append({
            'status': label,
            'time': _ts(dt_val) if not isinstance(dt_val, str) else (dt_val or '—'),
            'verified': bool(verified or 'qr verified' in norm_key),
        })

    # 1. Request Created
    if r.get('requested_at'):
        add_event('Delivery Requested', r['requested_at'])

    # 2. Payment / Escrow Funded
    if r.get('paid_at'):
        add_event('Escrow Funded & Paid', r['paid_at'])

    # 3. Courier Accepted
    if r.get('accepted_at'):
        add_event('Accepted by Courier', r['accepted_at'])

    # 4. Courier On The Way to Pickup / Dropoff
    if r.get('provider_on_way_at'):
        add_event('Courier En Route', r['provider_on_way_at'])

    # 5. Explicit rows from delivery_status_history
    for item in db_history:
        st_label = (item.get('status') or '').strip()
        if st_label:
            is_qr = 'qr' in st_label.lower() or 'verified' in st_label.lower()
            add_event(st_label, item.get('time') or '—', verified=is_qr)

    # 6. Pickup Verified / Cargo Picked Up
    if r.get('pickup_verified') or r.get('pickup_photo_taken_at'):
        pu_time = r.get('pickup_photo_taken_at') or r.get('provider_on_way_at') or r.get('accepted_at')
        label = 'Cargo Picked Up (QR Verified)' if r.get('pickup_verified') else 'Cargo Picked Up'
        add_event(label, pu_time, verified=bool(r.get('pickup_verified')))

    # 7. Arrived at Drop-off
    if r.get('dropoff_arrived_at'):
        add_event('Arrived at Drop-off Location', r['dropoff_arrived_at'])

    # 8. Failed Handoff
    if r.get('failed_at') or r.get('failure_reason'):
        reason_suffix = f" ({r['failure_reason']})" if r.get('failure_reason') else ""
        add_event(f"Delivery Attempt Failed{reason_suffix}", r.get('failed_at') or r.get('latest_status_at'))

    # 9. Returned to Sender
    if r.get('returned_at') or r.get('return_verified'):
        ret_label = 'Returned to Sender (QR Verified)' if r.get('return_verified') else 'Returned to Sender'
        add_event(ret_label, r.get('returned_at') or r.get('latest_status_at'), verified=bool(r.get('return_verified')))

    # 10. Completed / Delivered
    if r.get('completed_at') or r.get('dropoff_verified') or normalized_status == 'Completed':
        comp_time = r.get('completed_at') or r.get('dropoff_arrived_at') or r.get('latest_status_at')
        comp_label = 'Delivered (QR Verified)' if r.get('dropoff_verified') else 'Delivered & Completed'
        add_event(comp_label, comp_time, verified=bool(r.get('dropoff_verified')))

    # 11. Cancelled
    if normalized_status == 'Cancelled':
        add_event('Cancelled', r.get('latest_status_at') or r.get('requested_at'))

    return events


# ----------------------------------------------------------------------------
# list page
# ----------------------------------------------------------------------------
@admin_required
def deliveries(request):
    delivery_list = []
    stats = {'total': 0, 'active': 0, 'in_transit': 0, 'completed': 0, 'issues': 0}

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    dr.request_id, dr.pickup_type, dr.delivery_status AS request_status,
                    dr.emergency_flag, dr.total_distance, dr.estimated_cost,
                    dr.created_at AS requested_at, dr.scheduled_time,
                    dr.receiver_phone, dr.payment_status AS request_payment_status,
                    dr.payment_provider, dr.paid_at, dr.escrow_status AS request_escrow_status,
                    dr.pickup_note, dr.dropoff_note, dr.fallback_action, dr.fallback_recipient_name,
                    dr.base_fee, dr.base_fare, dr.distance_fee, dr.size_fee, dr.fragile_fee,
                    dr.schedule_fee, dr.emergency_fee, dr.return_deposit,
                    rcv.receiver_name,

                    d.delivery_id, d.accepted_at, d.estimated_eta, d.completed_at,
                    d.pod_photo_url, d.pickup_photo_url, d.pickup_photo_taken_at,
                    d.provider_on_way_at, d.provider_eta_mins, d.dropoff_arrived_at,
                    d.receiver_notified, d.receiver_notified_at,
                    d.failure_reason, d.failed_at, d.failure_photo_url,
                    d.returned_at, d.return_pod_photo_url,

                    s.user_id AS sender_id, s.first_name AS s_first, s.last_name AS s_last,
                    s.phone_number AS sender_phone,
                    p.user_id AS provider_id, p.first_name AS p_first, p.last_name AS p_last,
                    p.phone_number AS provider_phone,

                    v.vehicle_type, v.plate_number,
                    v.cargo_length_cm, v.cargo_width_cm, v.cargo_height_cm,

                    pl.street_address AS pu_street, pl.barangay AS pu_brgy, pl.city AS pu_city,
                    pl.province AS pu_prov, pl.latitude AS pu_lat, pl.longitude AS pu_lng,
                    dl.street_address AS do_street, dl.barangay AS do_brgy, dl.city AS do_city,
                    dl.province AS do_prov, dl.latitude AS do_lat, dl.longitude AS do_lng,

                    cp.description AS cargo_desc, cp.cargo_pic, cp.total_weight_kg,
                    cp.small_box_qty, cp.medium_box_qty, cp.large_box_qty, cp.is_fragile,

                    ep.escrow_id, ep.amount AS escrow_amount, ep.escrow_status AS escrow_status_raw,
                    ep.emergency_frozen, ep.bc_escrow_tx_hash,

                    t.base_amount, t.service_fee, t.penalty_fee, t.total_amount,
                    t.payment_method, t.status AS tx_status, t.processed_at,
                    t.bc_tx_hash AS tx_bc_hash,

                    cr.room_id,
                    qr.pickup_verified, qr.dropoff_verified, qr.return_verified,
                    qr.bc_pickup_tx_hash, qr.bc_dropoff_tx_hash,
                    dc.otp_verified, dc.attempts AS otp_attempts,

                    dsh.status AS latest_status, dsh.updated_at AS latest_status_at,
                    disp.dispute_ref, disp.issue_type, disp.description AS dispute_desc,
                    disp.status AS dispute_status,

                    COALESCE(dloc.latitude, ploc.latitude)   AS courier_lat,
                    COALESCE(dloc.longitude, ploc.longitude) AS courier_lng,
                    COALESCE(dloc.updated_at, ploc.updated_at) AS courier_loc_updated
                FROM delivery_requests dr
                LEFT JOIN deliveries d            ON d.request_id = dr.request_id
                LEFT JOIN receivers rcv           ON rcv.receiver_id = dr.receiver_id
                LEFT JOIN users s                 ON s.user_id = dr.sender_id
                LEFT JOIN users p                 ON p.user_id = COALESCE(d.provider_id, dr.preferred_provider_id)
                LEFT JOIN vehicles v              ON v.vehicle_id = d.vehicle_id
                LEFT JOIN locations pl            ON pl.location_id = dr.pickup_location_id
                LEFT JOIN locations dl            ON dl.location_id = dr.dropoff_location_id
                LEFT JOIN cargo_profiles cp       ON cp.cargo_id = dr.cargo_id
                LEFT JOIN delivery_confirmations dc ON dc.delivery_id = d.delivery_id
                LEFT JOIN delivery_locations dloc ON dloc.delivery_id = d.delivery_id
                LEFT JOIN provider_live_locations ploc ON ploc.provider_id = d.provider_id
                LEFT JOIN LATERAL (
                    SELECT escrow_id, amount, escrow_status, emergency_frozen, bc_escrow_tx_hash
                    FROM escrow_payments
                    WHERE delivery_id = d.delivery_id
                    ORDER BY escrow_id DESC LIMIT 1
                ) ep ON TRUE
                LEFT JOIN transactions t          ON t.escrow_id = ep.escrow_id
                LEFT JOIN LATERAL (
                    SELECT room_id FROM chat_rooms
                    WHERE delivery_id = d.delivery_id AND is_support = FALSE
                    ORDER BY room_id LIMIT 1
                ) cr ON TRUE
                LEFT JOIN LATERAL (
                    SELECT pickup_verified, dropoff_verified, return_verified,
                           bc_pickup_tx_hash, bc_dropoff_tx_hash
                    FROM qr_verifications
                    WHERE delivery_id = d.delivery_id
                    ORDER BY qr_id DESC LIMIT 1
                ) qr ON TRUE
                LEFT JOIN LATERAL (
                    SELECT status, updated_at FROM delivery_status_history
                    WHERE delivery_id = d.delivery_id
                    ORDER BY updated_at DESC LIMIT 1
                ) dsh ON TRUE
                LEFT JOIN LATERAL (
                    SELECT dispute_ref, issue_type, description, status
                    FROM disputes
                    WHERE request_id = dr.request_id
                    ORDER BY created_at DESC LIMIT 1
                ) disp ON TRUE
                ORDER BY dr.created_at DESC
            """)
            columns = [c[0] for c in cursor.description]
            rows = [dict(zip(columns, r)) for r in cursor.fetchall()]

            # ---- Status history for ALL deliveries in ONE query ----
            history_by_delivery = {}
            delivery_ids = [r['delivery_id'] for r in rows if r['delivery_id']]
            if delivery_ids:
                cursor.execute("""
                    SELECT delivery_id, status, updated_at
                    FROM delivery_status_history
                    WHERE delivery_id = ANY(%s)
                    ORDER BY delivery_id, updated_at ASC
                """, [delivery_ids])
                for did, st, ts in cursor.fetchall():
                    history_by_delivery.setdefault(did, []).append({'status': st, 'time': _ts(ts) or '—'})

        for r in rows:
            req_id, del_id = r['request_id'], r['delivery_id']
            display_id = del_id if del_id else f"REQ-{req_id}"

            sender_name = " ".join(filter(None, [r['s_first'], r['s_last']])) or f"USR-{r['sender_id']}"
            provider_name = " ".join(filter(None, [r['p_first'], r['p_last']])) or "Unassigned"
            pickup_addr = ", ".join(filter(None, [r['pu_street'], r['pu_brgy'], r['pu_city'], r['pu_prov']])) or '—'
            dropoff_addr = ", ".join(filter(None, [r['do_street'], r['do_brgy'], r['do_city'], r['do_prov']])) or '—'

            status = _normalize_delivery_status(
                delivery_status=r['request_status'],
                latest_status=r['latest_status'],
                completed_at=r['completed_at'],
                pickup_verified=r['pickup_verified'],
                dropoff_verified=r['dropoff_verified'],
                return_verified=r['return_verified'],
                returned_at=r['returned_at'],
                failed_at=r['failed_at'],
                failure_reason=r['failure_reason'],
                del_id=del_id,
            )

            # ---- Build complete timeline events ----
            raw_db_history = history_by_delivery.get(del_id, [])
            timeline_events = _build_timeline_events(r, raw_db_history, status)
            status_history_str = "; ".join(
                f"{ev['status']}|{ev['time']}" for ev in timeline_events
            )

            # ---- Disputes: only an UNRESOLVED dispute is an "active" emergency ----
            has_issue = bool(r['issue_type'] or r['dispute_desc'])
            dispute_status = r['dispute_status'] or ('Open' if has_issue else '')
            emergency_active = has_issue and dispute_status not in ('Resolved', 'Dismissed')

            # ---- Cargo dimensions ----
            dims = '—'
            cl, cw, ch = r['cargo_length_cm'], r['cargo_width_cm'], r['cargo_height_cm']
            if cl and cw and ch:
                dims = f"{float(cl):g} × {float(cw):g} × {float(ch):g} cm"

            # ---- Escrow: fall back to the request's own escrow_status when no escrow row exists yet ----
            escrow_display = _normalize_escrow_status(r['escrow_status_raw'] or r['request_escrow_status'])
            if r['emergency_frozen']:
                escrow_display = 'Frozen' if escrow_display == 'On Hold' else escrow_display
            escrow_amount_val = _num(r['escrow_amount'])
            if escrow_amount_val == 0:
                escrow_amount_val = _num(r['total_amount']) or _num(r['estimated_cost'])

            # ---- Payment: the transaction wins, otherwise what the request itself says ----
            payment_method = r['payment_method'] or (r['payment_provider'] or '').upper() or '—'
            payment_status = r['tx_status'] or (r['request_payment_status'] or '—').title()

            # ---- Fee breakdown straight from delivery_requests ----
            base_fee = (
                _num(r['base_fee'])
                or _num(r['base_fare'])
                or _num(r['base_amount'])
                or _num(r['estimated_cost'])
            )
            fee_lines = [(label, amt) for label, amt in (
                ('Base fare', base_fee),
                ('Distance', _num(r['distance_fee'])),
                ('Box size', _num(r['size_fee'])),
                ('Fragile handling', _num(r['fragile_fee'])),
                ('Scheduled delivery', _num(r['schedule_fee'])),
                ('Emergency / priority', _num(r['emergency_fee'])),
                ('Return deposit', _num(r['return_deposit'])),
            ) if amt > 0]
            if not fee_lines and r['estimated_cost']:
                fee_lines = [('Estimated cost', _num(r['estimated_cost']))]

            total_amount = _num(r['total_amount']) or escrow_amount_val or _num(r['estimated_cost'])

            # ---- On-chain proofs ----
            chain = [
                {'label': label, 'hash': h} for label, h in (
                    ('Escrow', r['bc_escrow_tx_hash']),
                    ('Payment', r['tx_bc_hash']),
                    ('QR pickup', r['bc_pickup_tx_hash']),
                    ('QR drop-off', r['bc_dropoff_tx_hash']),
                ) if h
            ]

            # ---- Proof of delivery / handoff ----
            proof = {
                'pickup_photo': _media_url(req_id, 'pickup', r['pickup_photo_url']),
                'pickup_photo_at': _ts(r['pickup_photo_taken_at']),
                'pod_photo': _media_url(req_id, 'pod', r['pod_photo_url']),
                'failure_photo': _media_url(req_id, 'failure', r['failure_photo_url']),
                'failure_reason': r['failure_reason'] or '',
                'failed_at': _ts(r['failed_at']),
                'return_photo': _media_url(req_id, 'return', r['return_pod_photo_url']),
                'returned_at': _ts(r['returned_at']),
            }
            handoff = {
                'pickup_verified': bool(r['pickup_verified']),
                'dropoff_verified': bool(r['dropoff_verified']),
                'return_verified': bool(r['return_verified']),
                'otp_verified': bool(r['otp_verified']),
                'otp_attempts': r['otp_attempts'] or 0,
                'on_way_at': _ts(r['provider_on_way_at']),
                'eta_mins': r['provider_eta_mins'],
                'arrived_at': _ts(r['dropoff_arrived_at']),
                'receiver_notified_at': _ts(r['receiver_notified_at']),
                'receiver_notified': bool(r['receiver_notified']),
                'receiver_name': r['receiver_name'] or '',
                'receiver_phone': r['receiver_phone'] or '',
                'pickup_note': r['pickup_note'] or '',
                'dropoff_note': r['dropoff_note'] or '',
                'fallback_action': (r['fallback_action'] or '').replace('_', ' ').capitalize(),
                'fallback_recipient': r['fallback_recipient_name'] or '',
                'scheduled_at': _ts(r['scheduled_time']),
                'distance_km': f"{_num(r['total_distance']):.1f}" if r['total_distance'] is not None else '',
                'paid_at': _ts(r['paid_at']),
            }

            loc_time = r['courier_loc_updated'] or r['latest_status_at']

            delivery_list.append({
                'id': display_id,
                'request_id': req_id,
                'delivery_id': del_id,
                'sender': sender_name,
                'sender_phone': r['sender_phone'] or '—',
                'provider': provider_name,
                'provider_phone': r['provider_phone'] or '',
                'provider_vehicle': f"{r['vehicle_type']} · {r['plate_number']}" if r['vehicle_type'] else '—',
                'status': status,
                'is_priority': bool(r['emergency_flag']),
                'delivery_type': r['pickup_type'] or '—',
                # dispute / issue
                'emergency': (r['dispute_desc'] or 'Reported issue') if has_issue else 'None',
                'emergency_type': r['issue_type'] or '',
                'emergency_status': dispute_status,
                'emergency_ref': r['dispute_ref'] or '',
                'emergency_active': emergency_active,
                'has_issue': has_issue,
                # escrow
                'escrow_status': escrow_display,
                'escrow_id': r['escrow_id'],
                'escrow_amount': _money(escrow_amount_val),
                'escrow_frozen': bool(r['emergency_frozen']),
                'escrow_tx_hash': r['bc_escrow_tx_hash'] or '',
                'transaction_tx_hash': r['tx_bc_hash'] or '',
                'chat_room_id': r['room_id'],
                # route
                'pickup_address': pickup_addr,
                'dropoff_address': dropoff_addr,
                'pickup_lat': _coord(r['pu_lat']),
                'pickup_lng': _coord(r['pu_lng']),
                'dropoff_lat': _coord(r['do_lat']),
                'dropoff_lng': _coord(r['do_lng']),
                'provider_lat': _coord(r['courier_lat']),
                'provider_lng': _coord(r['courier_lng']),
                'location_updated_at': _ts(loc_time),
                # timeline (both string and JSON formats supplied)
                'status_history': status_history_str,
                'status_history_json': json.dumps(timeline_events),
                # dates (templates format these with |date)
                'requested_at': r['requested_at'],
                'accepted_at': r['accepted_at'],
                'eta': r['estimated_eta'],
                'completed_at': r['completed_at'],
                'pickup_verified': bool(r['pickup_verified']),
                'dropoff_verified': bool(r['dropoff_verified']),
                # cargo
                'cargo_description': r['cargo_desc'] or 'No description provided.',
                'cargo_weight': _num(r['total_weight_kg']) or '',
                'cargo_dimensions': dims,
                'box_small': r['small_box_qty'] or 0,
                'box_medium': r['medium_box_qty'] or 0,
                'box_large': r['large_box_qty'] or 0,
                'is_fragile': bool(r['is_fragile']),
                'cargo_photo': _media_url(req_id, 'cargo', r['cargo_pic']),
                # money
                'base_fee': _money(base_fee),
                'fee_lines_json': json.dumps([[label, _money(amt)] for label, amt in fee_lines]),
                'service_fee': _money(r['service_fee']),
                'penalty_fee': _money(r['penalty_fee']),
                'total_amount': _money(total_amount),
                'payment_method': payment_method,
                'payment_status': payment_status,
                # extras
                'chain_json': json.dumps(chain),
                'proof_json': json.dumps(proof),
                'handoff_json': json.dumps(handoff),
            })

            stats['total'] += 1
            if status in ('Pending', 'Accepted'):
                stats['active'] += 1
            elif status == 'In Transit':
                stats['in_transit'] += 1
            elif status == 'Completed':
                stats['completed'] += 1
            if emergency_active or status in ('Failed', 'Returned'):
                stats['issues'] += 1

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[deliveries] DB error: {e}")

    return render(request, 'pages/deliveries.html', {'deliveries': delivery_list, 'stats': stats})


# ----------------------------------------------------------------------------
# photos (cargo, pickup, proof of delivery, failure, return)
# ----------------------------------------------------------------------------
@admin_required
def delivery_photo(request, request_id, kind):
    """Redirect an admin to a short-lived signed link for one delivery photo (private storage)."""
    sql = DELIVERY_PHOTO_QUERIES.get(kind)
    if not sql:
        raise Http404('Unknown photo type.')

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, [request_id])
            row = cursor.fetchone()
    except Exception as e:
        print(f"[delivery_photo] DB error: {e}")
        raise Http404('Photo not available.')

    stored = (row[0] if row else '') or ''
    stored = str(stored).strip()
    if not stored or stored.upper() == 'N/A':
        raise Http404('No photo on file.')

    try:
        bucket, path = parse_storage_ref(
            stored,
            default_bucket=os.environ.get('SUPABASE_DELIVERY_BUCKET') or os.environ.get('SUPABASE_VEHICLE_DOCS_BUCKET'),
        )
        url = create_signed_url(bucket, path, expires_in=120)
    except StorageError as e:
        # A plain public URL that isn't a storage reference: just use it as-is.
        if stored.lower().startswith(('http://', 'https://')):
            url = stored
        else:
            print(f"[delivery_photo] storage error for request {request_id} ({kind}): {e}")
            raise Http404('Photo not available.')

    response = redirect(url)
    response['Cache-Control'] = 'no-store'
    return response