# views/escrow_payments.py
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import connection
import json
from .login import admin_required


@admin_required
def escrow_payments(request):
    current_tab = request.GET.get('tab', 'active')
    escrow_list = []
    transactions_list = []

    status_map = {
        'completed':  'Released', 'released':   'Released',
        'on hold':    'On Hold',  'on_hold':    'On Hold',
        'frozen':     'Frozen',   'refunded':   'Refunded',
        'cancelled':  'Cancelled','canceled':   'Cancelled',
        'pending':    'On Hold',
    }

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    ep.escrow_id, ep.delivery_id, ep.amount, ep.escrow_status,
                    ep.emergency_frozen, ep.created_at, ep.bc_escrow_tx_hash,
                    ep.sender_id, ep.provider_id,
                    CONCAT_WS(' ', s.first_name, s.last_name) AS sender_name,
                    CONCAT_WS(' ', p.first_name, p.last_name) AS provider_name
                FROM escrow_payments ep
                LEFT JOIN users s ON s.user_id = ep.sender_id
                LEFT JOIN users p ON p.user_id = ep.provider_id
                WHERE LOWER(ep.escrow_status) NOT IN ('released', 'completed', 'refunded', 'cancelled')
                   OR ep.escrow_status IS NULL
                ORDER BY ep.created_at DESC
            """)
            for row in cursor.fetchall():
                (escrow_id, delivery_id, amount, raw_status, frozen,
                 created_at, tx_hash, sender_id, provider_id,
                 sender_name, provider_name) = row

                s_display = sender_name.strip() if sender_name and sender_name.strip() else f"USR-{sender_id}"
                p_display = provider_name.strip() if provider_name and provider_name.strip() else f"PRV-{provider_id}"
                raw_norm = (raw_status or 'On Hold').strip()
                display_status = status_map.get(raw_norm.lower(), raw_norm.title())
                if frozen is True:
                    display_status = 'Frozen'

                escrow_list.append({
                    'id': f"EID{escrow_id}",
                    'raw_id': escrow_id,
                    'delivery_id': delivery_id,
                    'sender_id': f"{s_display} (ID: {sender_id})",
                    'provider_id': f"{p_display} (ID: {provider_id})",
                    'amount': f"₱{float(amount or 0):,.2f}",
                    'escrow_status': display_status,
                    'bc_escrow_tx_hash': tx_hash or '',
                    'emergency_frozen': bool(frozen),
                    'created_at': created_at.strftime('%Y-%m-%d %I:%M %p') if created_at else '—',
                })

            cursor.execute("""
                SELECT
                    t.transaction_id, t.escrow_id, ep.delivery_id,
                    t.base_amount, t.service_fee, t.penalty_fee, t.total_amount,
                    t.payment_method, t.status, t.processed_at
                FROM transactions t
                LEFT JOIN escrow_payments ep ON ep.escrow_id = t.escrow_id
                ORDER BY t.processed_at DESC NULLS LAST, t.transaction_id DESC
            """)
            for r in cursor.fetchall():
                (tid, escrow_id, delivery_id,
                 base_amount, service_fee, penalty_fee, total_amount,
                 payment_method, raw_tx_status, processed_at) = r

                normalized_status = status_map.get((raw_tx_status or '').strip().lower(), (raw_tx_status or 'Released').title())

                transactions_list.append({
                    'id': f"TID{tid}",
                    'escrow_id': f"EID{escrow_id}" if escrow_id else '—',
                    'delivery_id': delivery_id or '—',
                    'base_amount': f"₱{float(base_amount or 0):,.2f}",
                    'service_fee': f"₱{float(service_fee or 0):,.2f}",
                    'penalty_fee': f"₱{float(penalty_fee or 0):,.2f}",
                    'total_amount': f"₱{float(total_amount or 0):,.2f}",
                    'method': payment_method or 'GCash',
                    'status': normalized_status,
                    'processed_at': processed_at.strftime('%Y-%m-%d %I:%M %p') if processed_at else '—',
                })

    except Exception as e:
        print(f"[escrow_payments] Database query error: {e}")

    return render(request, 'pages/escrow_payments.html', {
        'current_tab': current_tab,
        'escrow_list': escrow_list,
        'transactions': transactions_list,
    })


@admin_required
@require_POST
def process_escrow_action(request):
    try:
        data = json.loads(request.body)
        escrow_id = str(data.get('escrow_id', '')).replace('EID', '')
        action = data.get('action')

        if action not in ('release', 'refund'):
            return JsonResponse({'error': 'Invalid action'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("SELECT amount, emergency_frozen FROM escrow_payments WHERE escrow_id = %s", [escrow_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'error': 'Escrow record not found'}, status=404)

            escrow_amount, is_frozen = float(row[0] or 0.00), bool(row[1])
            if is_frozen:
                return JsonResponse({'error': 'This escrow account is currently FROZEN. Please unfreeze it first.'}, status=400)

            new_status = 'Released' if action == 'release' else 'Refunded'

            cursor.execute("""
                UPDATE escrow_payments SET escrow_status = %s, emergency_frozen = false
                WHERE escrow_id = %s
            """, [new_status, escrow_id])

            cursor.execute("""
                INSERT INTO transactions
                    (base_amount, service_fee, total_amount, penalty_fee, payment_method, status, processed_at, escrow_id)
                VALUES (%s, 0.00, %s, 0.00, 'GCash', %s, NOW(), %s)
            """, [escrow_amount, escrow_amount, new_status, escrow_id])

        return JsonResponse({'status': 'success', 'new_status': new_status})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@admin_required
@require_POST
def toggle_escrow_freeze(request):
    try:
        data = json.loads(request.body)
        escrow_id = data.get('escrow_id')

        if isinstance(escrow_id, str) and escrow_id.startswith('EID'):
            escrow_id = escrow_id.replace('EID', '')

        with connection.cursor() as cursor:
            cursor.execute("SELECT emergency_frozen FROM escrow_payments WHERE escrow_id = %s", [escrow_id])
            row = cursor.fetchone()

            if not row:
                return JsonResponse({'error': 'Escrow record not found'}, status=404)

            is_currently_frozen = row[0]
            new_frozen_state = not is_currently_frozen
            new_status = 'Frozen' if new_frozen_state else 'On Hold'

            cursor.execute("""
                UPDATE escrow_payments SET emergency_frozen = %s, escrow_status = %s
                WHERE escrow_id = %s
            """, [new_frozen_state, new_status, escrow_id])

        return JsonResponse({
            'status': 'success',
            'is_frozen': new_frozen_state,
            'escrow_status': new_status
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)