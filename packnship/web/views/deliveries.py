# views/deliveries.py
from django.shortcuts import render
from django.db import connection
from .login import admin_required


def _normalize_escrow_status(raw):
    """Map DB values to a canonical display status."""
    s = (raw or '').strip().lower().replace('_', ' ')
    if s in ('released', 'completed'):
        return 'Released'
    if s == 'refunded':
        return 'Refunded'
    if s == 'frozen':
        return 'Frozen'
    if s in ('on hold', 'onhold', 'pending', ''):
        return 'On Hold'
    if s == 'cancelled' or s == 'canceled':
        return 'Cancelled'
    return (raw or 'On Hold').title()


@admin_required
def deliveries(request):
    delivery_list = []

    try:
        with connection.cursor() as cursor:
            # Changed base table to delivery_requests to capture all statuses (Pending, Cancelled, etc.)
            cursor.execute("""
                SELECT
                    dr.request_id,
                    d.delivery_id,
                    d.accepted_at, d.estimated_eta, d.completed_at,
                    s.user_id, s.first_name, s.last_name, s.phone_number,
                    p.user_id, p.first_name, p.last_name,
                    v.vehicle_type, v.plate_number,
                    v.cargo_length_cm, v.cargo_width_cm, v.cargo_height_cm,
                    pl.street_address, pl.barangay, pl.city, pl.province, pl.latitude, pl.longitude,
                    dl.street_address, dl.barangay, dl.city, dl.province, dl.latitude, dl.longitude,
                    dr.pickup_type, dr.delivery_status, dr.emergency_flag, dr.total_distance,
                    dr.estimated_cost, dr.created_at, dr.receiver_phone,
                    cp.description, cp.cargo_pic, cp.total_weight_kg,
                    cp.small_box_qty, cp.medium_box_qty, cp.large_box_qty, cp.is_fragile,
                    dsh.status AS latest_status, dsh.updated_at AS latest_status_at,
                    ep.escrow_id, ep.amount, ep.escrow_status, ep.emergency_frozen, ep.bc_escrow_tx_hash,
                    t.base_amount, t.service_fee, t.penalty_fee, t.total_amount,
                    t.payment_method, t.status AS tx_status, t.processed_at,
                    cr.room_id,
                    qr.pickup_verified, qr.dropoff_verified,
                    disp.issue_type, disp.description AS dispute_desc, disp.status AS dispute_status
                FROM delivery_requests dr
                LEFT JOIN deliveries d ON d.request_id = dr.request_id
                LEFT JOIN users s ON s.user_id = dr.sender_id
                LEFT JOIN users p ON p.user_id = d.provider_id
                LEFT JOIN vehicles v ON v.vehicle_id = d.vehicle_id
                LEFT JOIN locations pl ON pl.location_id = dr.pickup_location_id
                LEFT JOIN locations dl ON dl.location_id = dr.dropoff_location_id
                LEFT JOIN cargo_profiles cp ON cp.cargo_id = dr.cargo_id
                LEFT JOIN escrow_payments ep ON ep.delivery_id = d.delivery_id
                LEFT JOIN transactions t ON t.escrow_id = ep.escrow_id
                LEFT JOIN chat_rooms cr ON cr.delivery_id = d.delivery_id AND cr.is_support = FALSE
                LEFT JOIN qr_verifications qr ON qr.delivery_id = d.delivery_id
                LEFT JOIN LATERAL (
                    SELECT status, updated_at FROM delivery_status_history
                    WHERE delivery_id = d.delivery_id
                    ORDER BY updated_at DESC LIMIT 1
                ) dsh ON true
                LEFT JOIN LATERAL (
                    SELECT issue_type, description, status
                    FROM disputes
                    WHERE delivery_id = d.delivery_id
                    ORDER BY created_at DESC LIMIT 1
                ) disp ON true
                ORDER BY dr.created_at DESC
            """)

            for row in cursor.fetchall():
                (req_id, del_id, accepted_at, eta, completed_at,
                 s_id, s_first, s_last, sender_phone,
                 p_id, p_first, p_last, vehicle_type, plate_number,
                 cl, cw, ch,
                 pu_street, pu_brgy, pu_city, pu_prov, pu_lat, pu_lng,
                 do_street, do_brgy, do_city, do_prov, do_lat, do_lng,
                 pickup_type, delivery_status, emergency_flag, total_distance, estimated_cost, requested_at, receiver_phone,
                 cargo_desc, cargo_pic, weight, sb, mb, lb, fragile,
                 latest_status, latest_status_at,
                 escrow_id, escrow_amount, escrow_status_raw, emergency_frozen, bc_escrow_tx,
                 base_amount, service_fee, penalty_fee, total_amount, payment_method, payment_status, processed_at,
                 room_id, pickup_verified, dropoff_verified,
                 issue_type, issue_desc, issue_status) = row

                display_id = del_id if del_id else f"REQ-{req_id}"
                
                # Updated: removed middle_name from name construction
                sender_name   = " ".join(filter(None, [s_first, s_last])) or f"USR-{s_id}"
                provider_name = " ".join(filter(None, [p_first, p_last])) or "Unassigned"
                
                pickup_addr  = ", ".join(filter(None, [pu_street, pu_brgy, pu_city, pu_prov])) or '—'
                dropoff_addr = ", ".join(filter(None, [do_street, do_brgy, do_city, do_prov])) or '—'

                # Status logic prioritizing Cancellation and Completion
                if delivery_status == 'Cancelled':
                    status = 'Cancelled'
                elif completed_at:
                    status = 'Completed'
                elif latest_status:
                    status = latest_status
                elif delivery_status:
                    status = delivery_status
                else:
                    status = 'Pending'

                # ---- Status history string ----
                status_history_str = ""
                if del_id:
                    cursor.execute("""
                        SELECT status, updated_at FROM delivery_status_history
                        WHERE delivery_id = %s ORDER BY updated_at ASC
                    """, [del_id])
                    status_history_str = ";".join(
                        f"{st}|{ts.strftime('%b %d, %Y — %I:%M %p') if ts else '—'}"
                        for st, ts in cursor.fetchall()
                    )

                # ---- Emergency / dispute info ----
                emergency_display = 'None'
                emergency_type = ''
                emergency_status = ''
                if emergency_flag and (issue_type or issue_desc):
                    emergency_type = issue_type or ''
                    emergency_display = issue_desc or 'Active emergency reported'
                    emergency_status = issue_status or 'Open'
                elif issue_type or issue_desc:
                    emergency_type = issue_type or ''
                    emergency_display = issue_desc or 'Reported issue'
                    emergency_status = issue_status or 'Open'

                # ---- Cargo dimensions (now using vehicle dimensions) ----
                dims = '—'
                if cl and cw and ch:
                    dims = f"{float(cl):g} × {float(cw):g} × {float(ch):g} cm"

                # ---- Escrow normalization ----
                escrow_display = _normalize_escrow_status(escrow_status_raw)
                escrow_amount_val = float(escrow_amount or 0)

                if escrow_amount_val == 0 and total_amount:
                    escrow_amount_val = float(total_amount or 0)

                delivery_list.append({
                    'id': display_id,
                    'request_id': req_id,
                    'delivery_id': del_id,
                    'sender': sender_name,
                    'sender_phone': sender_phone or '—',
                    'provider': provider_name,
                    'provider_vehicle': f"{vehicle_type} · {plate_number}" if vehicle_type else '—',
                    'status': status,
                    'delivery_type': pickup_type or '—',
                    'emergency': emergency_display,
                    'emergency_type': emergency_type,
                    'emergency_status': emergency_status,
                    'escrow_status': escrow_display,
                    'escrow_id': escrow_id,
                    'escrow_amount': escrow_amount_val,
                    'escrow_frozen': bool(emergency_frozen),
                    'escrow_tx_hash': bc_escrow_tx or '',
                    'chat_room_id': room_id,
                    'pickup_address': pickup_addr,
                    'dropoff_address': dropoff_addr,
                    'provider_lat': float(pu_lat) if pu_lat else '',
                    'provider_lng': float(pu_lng) if pu_lng else '',
                    'dropoff_lat': float(do_lat) if do_lat else '',
                    'dropoff_lng': float(do_lng) if do_lng else '',
                    'location_updated_at': latest_status_at.strftime('%b %d, %Y — %I:%M %p') if latest_status_at else '',
                    'status_history': status_history_str,
                    'requested_at': requested_at,
                    'accepted_at': accepted_at,
                    'eta': eta,
                    'completed_at': completed_at,
                    'pickup_verified': bool(pickup_verified),
                    'dropoff_verified': bool(dropoff_verified),
                    'cargo_description': cargo_desc or 'No description provided.',
                    'cargo_weight': float(weight) if weight else '',
                    'cargo_dimensions': dims,
                    'box_small': sb or 0,
                    'box_medium': mb or 0,
                    'box_large': lb or 0,
                    'is_fragile': bool(fragile),
                    'cargo_photo': cargo_pic or '',
                    'base_fee': float(base_amount or 0),
                    'service_fee': float(service_fee or 0),
                    'penalty_fee': float(penalty_fee or 0),
                    'total_amount': float(total_amount or 0),
                    'payment_method': payment_method or '—',
                    'payment_status': (payment_status or '—'),
                    'transaction_tx_hash': '',
                })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[deliveries] DB error: {e}")

    return render(request, 'pages/deliveries.html', {'deliveries': delivery_list})