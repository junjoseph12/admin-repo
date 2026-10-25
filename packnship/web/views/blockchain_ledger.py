# web/views/blockchain_ledger.py
import json
from datetime import datetime, timezone as dt_timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .login import admin_required
from .utils import log_admin_action
from ..blockchain import (
    get_network_info,
    anchor_provider_verification,
    anchor_escrow_payment,
    anchor_delivery_log,
    anchor_qr_handoff,
    anchor_rating_review,
    anchor_financial_transaction,
    anchor_withdrawal,
)


# --- Safe Local Time & Timestamp Helpers ---
def to_aware_utc(dt):
    """Safely converts both naive and aware datetimes to aware UTC."""
    if not dt or not isinstance(dt, datetime):
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


def format_local_time(dt):
    """Formats any database datetime into local time (e.g. Oct 25, 2026 07:32 AM)."""
    aware_dt = to_aware_utc(dt)
    if not aware_dt:
        return '—'
    try:
        local_dt = timezone.localtime(aware_dt)
    except Exception:
        local_dt = aware_dt
    return local_dt.strftime('%b %d, %Y %I:%M %p')


def safe_sort_ts(dt):
    """Returns a float UNIX timestamp for reliable sorting across naive/aware datetimes."""
    aware_dt = to_aware_utc(dt)
    if not aware_dt:
        return 0.0
    try:
        return float(aware_dt.timestamp())
    except Exception:
        return 0.0


def auto_sync_pending_records(max_batch=25):
    """
    Automatically anchors any newly inserted unanchored records from Mobile or Admin
    so the ledger stays 100% in sync without requiring manual intervention.
    """
    anchored_count = 0
    try:
        with connection.cursor() as cursor:
            # 1. Approved Provider Verifications
            cursor.execute("""
                SELECT provider_id, drivers_license_number
                FROM public.provider_verifications
                WHERE LOWER(verification_status) IN ('approved', 'verified')
                  AND (bc_verif_tx_hash IS NULL OR bc_verif_tx_hash = '')
                LIMIT %s
            """, [max_batch])
            for (pid, lic_no) in cursor.fetchall():
                try:
                    anchor_provider_verification(cursor, pid, lic_no)
                    anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] KYC {pid} error: {e}")

            # 2. Escrow Payments
            cursor.execute("""
                SELECT escrow_id FROM public.escrow_payments
                WHERE bc_escrow_tx_hash IS NULL OR bc_escrow_tx_hash = ''
                LIMIT %s
            """, [max_batch])
            for (eid,) in cursor.fetchall():
                try:
                    anchor_escrow_payment(cursor, eid)
                    anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] Escrow {eid} error: {e}")

            # 3. Deliveries
            cursor.execute("""
                SELECT d.delivery_id FROM public.deliveries d
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.blockchain_logs bl WHERE bl.delivery_id = d.delivery_id
                )
                LIMIT %s
            """, [max_batch])
            for (did,) in cursor.fetchall():
                try:
                    anchor_delivery_log(cursor, did)
                    anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] Delivery {did} error: {e}")

            # 4. Verified QR Handoffs
            cursor.execute("""
                SELECT qr_id, pickup_verified, dropoff_verified, bc_pickup_tx_hash, bc_dropoff_tx_hash
                FROM public.qr_verifications
                WHERE (pickup_verified = TRUE AND (bc_pickup_tx_hash IS NULL OR bc_pickup_tx_hash = ''))
                   OR (dropoff_verified = TRUE AND (bc_dropoff_tx_hash IS NULL OR bc_dropoff_tx_hash = ''))
                LIMIT %s
            """, [max_batch])
            for (qid, p_ver, d_ver, p_tx, d_tx) in cursor.fetchall():
                try:
                    if p_ver and not p_tx:
                        anchor_qr_handoff(cursor, qid, 'pickup')
                        anchored_count += 1
                    if d_ver and not d_tx:
                        anchor_qr_handoff(cursor, qid, 'dropoff')
                        anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] QR {qid} error: {e}")

            # 5. Ratings & Reviews
            cursor.execute("""
                SELECT review_id FROM public.ratings_reviews
                WHERE bc_rating_tx_hash IS NULL OR bc_rating_tx_hash = ''
                LIMIT %s
            """, [max_batch])
            for (rid,) in cursor.fetchall():
                try:
                    anchor_rating_review(cursor, rid)
                    anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] Review {rid} error: {e}")

            # 6. Financial Transactions
            cursor.execute("""
                SELECT transaction_id FROM public.transactions
                WHERE bc_tx_hash IS NULL OR bc_tx_hash = ''
                LIMIT %s
            """, [max_batch])
            for (tid,) in cursor.fetchall():
                try:
                    anchor_financial_transaction(cursor, tid)
                    anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] Transaction {tid} error: {e}")

            # 7. Withdrawal Requests
            cursor.execute("""
                SELECT withdrawal_id FROM public.withdrawal_requests
                WHERE bc_tx_hash IS NULL OR bc_tx_hash = ''
                LIMIT %s
            """, [max_batch])
            for (wid,) in cursor.fetchall():
                try:
                    anchor_withdrawal(cursor, wid)
                    anchored_count += 1
                except Exception as e:
                    print(f"[auto_sync] Withdrawal {wid} error: {e}")

    except Exception as e:
        print(f"[auto_sync_pending_records] error: {e}")

    return anchored_count
# -------------------------------------------


@admin_required
def blockchain_ledger_page(request):
    current_tab = request.GET.get('tab', 'all')
    network_info = get_network_info()

    # Automatically anchor any new mobile/admin records on load
    if request.GET.get('autosync', '1') != '0':
        auto_sync_pending_records(max_batch=20)

    ledger_entries = []
    unanchored_counts = {
        'verifications': 0,
        'escrow': 0,
        'deliveries': 0,
        'qr': 0,
        'reviews': 0,
        'transactions': 0,
        'withdrawals': 0,
    }
    category_counts = {
        'all': 0,
        'deliveries': 0,
        'verifications': 0,
        'escrow': 0,
        'transactions': 0,
        'withdrawals': 0,
        'qr': 0,
        'reviews': 0,
    }

    with connection.cursor() as cursor:
        # 1. Delivery Logs (public.blockchain_logs)
        try:
            cursor.execute("""
                SELECT bl.id, bl.delivery_id, bl.tx_hash, bl.status, bl.created_at,
                       u.first_name, u.last_name
                FROM public.blockchain_logs bl
                LEFT JOIN public.deliveries d ON d.delivery_id = bl.delivery_id
                LEFT JOIN public.users u ON u.user_id = d.provider_id
                WHERE bl.tx_hash IS NOT NULL AND bl.tx_hash != ''
                ORDER BY bl.created_at DESC NULLS LAST, bl.id DESC
            """)
            for (bid, deliv_id, tx_hash, status, created_at, fname, lname) in cursor.fetchall():
                prov_name = " ".join(filter(None, [fname, lname])) or f"Delivery #{deliv_id}"
                ledger_entries.append({
                    'category': 'deliveries',
                    'badge': 'Delivery Log',
                    'badge_color': 'orange',
                    'ref_id': f"DEL-{deliv_id}",
                    'raw_id': deliv_id,
                    'entity_name': prov_name,
                    'details': f"Blockchain Log #{bid} · Delivery #{deliv_id}",
                    'tx_hash': tx_hash,
                    'status': (status or 'confirmed').capitalize(),
                    'timestamp': format_local_time(created_at),
                    'sort_ts': safe_sort_ts(created_at),
                })
        except Exception as e:
            print(f"[blockchain_ledger] Deliveries query error: {e}")

        # 2. Provider Verifications (public.provider_verifications.bc_verif_tx_hash)
        try:
            cursor.execute("""
                SELECT pv.verification_id, pv.provider_id, pv.drivers_license_number,
                       pv.verification_status, pv.bc_verif_tx_hash,
                       COALESCE(pv.verified_at, pv.submitted_at) AS ts,
                       u.first_name, u.last_name
                FROM public.provider_verifications pv
                LEFT JOIN public.users u ON u.user_id = pv.provider_id
                WHERE pv.bc_verif_tx_hash IS NOT NULL AND pv.bc_verif_tx_hash != ''
                ORDER BY ts DESC NULLS LAST
            """)
            for (vid, pid, lic_no, vstat, tx_hash, ts, fname, lname) in cursor.fetchall():
                full_name = " ".join(filter(None, [fname, lname])) or f"Provider US{pid}"
                ledger_entries.append({
                    'category': 'verifications',
                    'badge': 'Provider KYC',
                    'badge_color': 'green',
                    'ref_id': f"US{pid}",
                    'raw_id': pid,
                    'entity_name': full_name,
                    'details': f"License: {lic_no} ({vstat})",
                    'tx_hash': tx_hash,
                    'status': 'Confirmed',
                    'timestamp': format_local_time(ts),
                    'sort_ts': safe_sort_ts(ts),
                })
        except Exception as e:
            print(f"[blockchain_ledger] Verifications query error: {e}")

        # 3. Escrow Payments (public.escrow_payments.bc_escrow_tx_hash)
        try:
            cursor.execute("""
                SELECT ep.escrow_id, ep.delivery_id, ep.amount, ep.escrow_status,
                       ep.bc_escrow_tx_hash, ep.created_at,
                       s.first_name, s.last_name
                FROM public.escrow_payments ep
                LEFT JOIN public.users s ON s.user_id = ep.sender_id
                WHERE ep.bc_escrow_tx_hash IS NOT NULL AND ep.bc_escrow_tx_hash != ''
                ORDER BY ep.created_at DESC NULLS LAST
            """)
            for (eid, did, amt, estat, tx_hash, ts, sfname, slname) in cursor.fetchall():
                sname = " ".join(filter(None, [sfname, slname])) or f"Escrow #{eid}"
                ledger_entries.append({
                    'category': 'escrow',
                    'badge': 'Escrow Payment',
                    'badge_color': 'blue',
                    'ref_id': f"ESC-{eid}",
                    'raw_id': eid,
                    'entity_name': sname,
                    'details': f"₱{float(amt or 0):,.2f} · {estat} (Delivery #{did})",
                    'tx_hash': tx_hash,
                    'status': 'Confirmed',
                    'timestamp': format_local_time(ts),
                    'sort_ts': safe_sort_ts(ts),
                })
        except Exception as e:
            print(f"[blockchain_ledger] Escrow query error: {e}")

        # 4. QR Verifications (public.qr_verifications.bc_pickup_tx_hash / bc_dropoff_tx_hash)
        try:
            cursor.execute("""
                SELECT qr.qr_id, qr.delivery_id, qr.bc_pickup_tx_hash, qr.bc_dropoff_tx_hash,
                       d.accepted_at, d.completed_at
                FROM public.qr_verifications qr
                LEFT JOIN public.deliveries d ON d.delivery_id = qr.delivery_id
                WHERE (qr.bc_pickup_tx_hash IS NOT NULL AND qr.bc_pickup_tx_hash != '')
                   OR (qr.bc_dropoff_tx_hash IS NOT NULL AND qr.bc_dropoff_tx_hash != '')
                ORDER BY qr.qr_id DESC
            """)
            for (qid, did, pickup_tx, dropoff_tx, acc_at, comp_at) in cursor.fetchall():
                if pickup_tx:
                    ledger_entries.append({
                        'category': 'qr',
                        'badge': 'QR Pickup',
                        'badge_color': 'purple',
                        'ref_id': f"QR-{qid}-P",
                        'raw_id': qid,
                        'entity_name': f"Delivery #{did} Pickup",
                        'details': f"QR Handoff #{qid} · Pickup Verified",
                        'tx_hash': pickup_tx,
                        'status': 'Confirmed',
                        'timestamp': format_local_time(acc_at),
                        'sort_ts': safe_sort_ts(acc_at),
                    })
                if dropoff_tx:
                    drops_ts = comp_at or acc_at
                    ledger_entries.append({
                        'category': 'qr',
                        'badge': 'QR Dropoff',
                        'badge_color': 'purple',
                        'ref_id': f"QR-{qid}-D",
                        'raw_id': qid,
                        'entity_name': f"Delivery #{did} Dropoff",
                        'details': f"QR Handoff #{qid} · Dropoff Verified",
                        'tx_hash': dropoff_tx,
                        'status': 'Confirmed',
                        'timestamp': format_local_time(drops_ts),
                        'sort_ts': safe_sort_ts(drops_ts),
                    })
        except Exception as e:
            print(f"[blockchain_ledger] QR query error: {e}")

        # 5. Ratings & Reviews (public.ratings_reviews.bc_rating_tx_hash)
        try:
            cursor.execute("""
                SELECT rr.review_id, rr.delivery_id, rr.rating, rr.bc_rating_tx_hash, rr.created_at,
                       u.first_name, u.last_name
                FROM public.ratings_reviews rr
                LEFT JOIN public.users u ON u.user_id = rr.reviewee_id
                WHERE rr.bc_rating_tx_hash IS NOT NULL AND rr.bc_rating_tx_hash != ''
                ORDER BY rr.created_at DESC NULLS LAST
            """)
            for (rid, did, rating, tx_hash, ts, fname, lname) in cursor.fetchall():
                rname = " ".join(filter(None, [fname, lname])) or f"Review #{rid}"
                ledger_entries.append({
                    'category': 'reviews',
                    'badge': 'Rating & Review',
                    'badge_color': 'amber',
                    'ref_id': f"REV-{rid}",
                    'raw_id': rid,
                    'entity_name': rname,
                    'details': f"★ {rating}/5 · Delivery #{did}",
                    'tx_hash': tx_hash,
                    'status': 'Confirmed',
                    'timestamp': format_local_time(ts),
                    'sort_ts': safe_sort_ts(ts),
                })
        except Exception as e:
            print(f"[blockchain_ledger] Reviews query error: {e}")

        # 6. Financial Transactions (public.transactions.bc_tx_hash)
        try:
            cursor.execute("""
                SELECT t.transaction_id, t.escrow_id, t.total_amount, t.payment_method, t.status,
                       t.bc_tx_hash, COALESCE(t.processed_at, ep.created_at) AS ts,
                       u.first_name, u.last_name
                FROM public.transactions t
                LEFT JOIN public.escrow_payments ep ON ep.escrow_id = t.escrow_id
                LEFT JOIN public.users u ON u.user_id = ep.sender_id
                WHERE t.bc_tx_hash IS NOT NULL AND t.bc_tx_hash != ''
                ORDER BY ts DESC NULLS LAST, t.transaction_id DESC
            """)
            for (tid, escrow_id, amt, method, status, tx_hash, ts, fname, lname) in cursor.fetchall():
                sname = " ".join(filter(None, [fname, lname])) or f"Transaction #{tid}"
                ledger_entries.append({
                    'category': 'transactions',
                    'badge': 'Financial Tx',
                    'badge_color': 'blue',
                    'ref_id': f"TXN-{tid}",
                    'raw_id': tid,
                    'entity_name': sname,
                    'details': f"₱{float(amt or 0):,.2f} via {(method or 'GCASH').upper()} ({status}) · Escrow #{escrow_id}",
                    'tx_hash': tx_hash,
                    'status': 'Confirmed',
                    'timestamp': format_local_time(ts),
                    'sort_ts': safe_sort_ts(ts),
                })
        except Exception as e:
            print(f"[blockchain_ledger] Transactions query error: {e}")

        # 7. Withdrawal Requests (public.withdrawal_requests.bc_tx_hash)
        try:
            cursor.execute("""
                SELECT w.withdrawal_id, w.amount, w.method, w.status, w.bc_tx_hash, 
                       COALESCE(w.processed_at, w.requested_at, w.updated_at) AS ts,
                       u.first_name, u.last_name
                FROM public.withdrawal_requests w
                LEFT JOIN public.provider_wallet pw ON pw.wallet_id = w.provider_wallet_id
                LEFT JOIN public.users u ON u.user_id = pw.provider_id
                WHERE w.bc_tx_hash IS NOT NULL AND w.bc_tx_hash != ''
                ORDER BY ts DESC NULLS LAST, w.withdrawal_id DESC
            """)
            for (wid, amt, method, status, tx_hash, ts, fname, lname) in cursor.fetchall():
                pname = " ".join(filter(None, [fname, lname])) or f"Withdrawal #{wid}"
                ledger_entries.append({
                    'category': 'withdrawals',
                    'badge': 'Withdrawal',
                    'badge_color': 'purple',
                    'ref_id': f"WDR-{wid}",
                    'raw_id': wid,
                    'entity_name': pname,
                    'details': f"₱{float(amt or 0):,.2f} via {(method or 'GCASH').upper()} ({status})",
                    'tx_hash': tx_hash,
                    'status': 'Confirmed',
                    'timestamp': format_local_time(ts),
                    'sort_ts': safe_sort_ts(ts),
                })
        except Exception as e:
            print(f"[blockchain_ledger] Withdrawals query error: {e}")

        # --- Count any remaining unanchored records ---
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM public.provider_verifications
                WHERE LOWER(verification_status) IN ('approved', 'verified')
                  AND (bc_verif_tx_hash IS NULL OR bc_verif_tx_hash = '')
            """)
            unanchored_counts['verifications'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM public.escrow_payments
                WHERE bc_escrow_tx_hash IS NULL OR bc_escrow_tx_hash = ''
            """)
            unanchored_counts['escrow'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM public.deliveries d
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.blockchain_logs bl WHERE bl.delivery_id = d.delivery_id
                )
            """)
            unanchored_counts['deliveries'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM public.qr_verifications
                WHERE (pickup_verified = TRUE AND (bc_pickup_tx_hash IS NULL OR bc_pickup_tx_hash = ''))
                   OR (dropoff_verified = TRUE AND (bc_dropoff_tx_hash IS NULL OR bc_dropoff_tx_hash = ''))
            """)
            unanchored_counts['qr'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM public.ratings_reviews
                WHERE bc_rating_tx_hash IS NULL OR bc_rating_tx_hash = ''
            """)
            unanchored_counts['reviews'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM public.transactions
                WHERE bc_tx_hash IS NULL OR bc_tx_hash = ''
            """)
            unanchored_counts['transactions'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM public.withdrawal_requests
                WHERE bc_tx_hash IS NULL OR bc_tx_hash = ''
            """)
            unanchored_counts['withdrawals'] = cursor.fetchone()[0] or 0
        except Exception as e:
            print(f"[blockchain_ledger] Unanchored count error: {e}")

    # Calculate per-category tab counts and sort all entries newest-first
    ledger_entries.sort(key=lambda x: x['sort_ts'], reverse=True)
    total_anchored = len(ledger_entries)
    total_unanchored = sum(unanchored_counts.values())

    category_counts['all'] = total_anchored
    for entry in ledger_entries:
        cat = entry.get('category')
        if cat in category_counts:
            category_counts[cat] += 1

    # Filter by selected tab BEFORE paginating
    if current_tab != 'all':
        filtered_entries = [e for e in ledger_entries if e['category'] == current_tab]
    else:
        filtered_entries = ledger_entries

    # Paginate (50 entries per page)
    page = request.GET.get('page', 1)
    paginator = Paginator(filtered_entries, 50)
    try:
        paginated_entries = paginator.page(page)
    except PageNotAnInteger:
        paginated_entries = paginator.page(1)
    except EmptyPage:
        paginated_entries = paginator.page(paginator.num_pages)

    return render(request, 'pages/blockchain_ledger.html', {
        'entries': paginated_entries,
        'page_obj': paginated_entries,
        'current_tab': current_tab,
        'category_counts': category_counts,
        'network': network_info,
        'total_anchored': total_anchored,
        'total_unanchored': total_unanchored,
        'unanchored_counts': unanchored_counts,
    })


@admin_required
def sync_unanchored_records(request):
    """One-click Admin action to anchor all pending/un-anchored records across all tables."""
    if request.method != 'POST':
        return redirect('blockchain_ledger')

    anchored_total = auto_sync_pending_records(max_batch=500)
    if anchored_total > 0:
        messages.success(request, f'Successfully anchored {anchored_total} record(s) onto the blockchain ledger.')
        log_admin_action(request, f"Synchronized & Anchored {anchored_total} records onto Blockchain Ledger")
    else:
        messages.info(request, 'All eligible records are already anchored on-chain.')

    return redirect('blockchain_ledger')


@csrf_exempt
def auto_anchor_webhook_api(request):
    """
    Webhook endpoint that Mobile or Supabase Database Webhooks can POST to
    whenever new data is inserted, triggering immediate Polygon Amoy anchoring.
    """
    if request.method not in ('POST', 'GET'):
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    anchored = auto_sync_pending_records(max_batch=25)
    return JsonResponse({
        'success': True,
        'anchored_count': anchored,
    })


@csrf_exempt
@admin_required
def verify_tx_hash_api(request):
    """AJAX endpoint to verify any 0x transaction hash across all Pack-N-Ship tables."""
    tx_hash = (request.GET.get('tx_hash') or '').strip()
    if not tx_hash:
        return JsonResponse({'found': False, 'error': 'Provide a transaction hash.'}, status=400)

    try:
        with connection.cursor() as cursor:
            # 1. Check blockchain_logs
            cursor.execute("""
                SELECT id, delivery_id, status, created_at
                FROM public.blockchain_logs
                WHERE tx_hash = %s LIMIT 1
            """, [tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': 'Delivery Audit Log (public.blockchain_logs)',
                    'record_id': f"Log #{row[0]} · Delivery #{row[1]}",
                    'status': row[2],
                    'timestamp': format_local_time(row[3]) if row[3] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

            # 2. Check provider_verifications
            cursor.execute("""
                SELECT verification_id, provider_id, drivers_license_number,
                       COALESCE(verified_at, submitted_at)
                FROM public.provider_verifications
                WHERE bc_verif_tx_hash = %s LIMIT 1
            """, [tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': 'Provider KYC Verification (public.provider_verifications)',
                    'record_id': f"Verification #{row[0]} · Provider US{row[1]} (License: {row[2]})",
                    'status': 'Verified On-Chain',
                    'timestamp': format_local_time(row[3]) if row[3] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

            # 3. Check escrow_payments
            cursor.execute("""
                SELECT escrow_id, delivery_id, amount, escrow_status, created_at
                FROM public.escrow_payments
                WHERE bc_escrow_tx_hash = %s LIMIT 1
            """, [tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': 'Escrow Smart Ledger (public.escrow_payments)',
                    'record_id': f"Escrow #{row[0]} · Delivery #{row[1]} (₱{float(row[2] or 0):,.2f})",
                    'status': row[3],
                    'timestamp': format_local_time(row[4]) if row[4] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

            # 4. Check qr_verifications
            cursor.execute("""
                SELECT qr.qr_id, qr.delivery_id,
                       CASE WHEN qr.bc_pickup_tx_hash = %s THEN 'Pickup Handoff' ELSE 'Dropoff Handoff' END,
                       CASE WHEN qr.bc_pickup_tx_hash = %s THEN d.accepted_at ELSE COALESCE(d.completed_at, d.accepted_at) END
                FROM public.qr_verifications qr
                LEFT JOIN public.deliveries d ON d.delivery_id = qr.delivery_id
                WHERE qr.bc_pickup_tx_hash = %s OR qr.bc_dropoff_tx_hash = %s LIMIT 1
            """, [tx_hash, tx_hash, tx_hash, tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': f"QR Chain of Custody · {row[2]} (public.qr_verifications)",
                    'record_id': f"QR #{row[0]} · Delivery #{row[1]}",
                    'status': 'Verified On-Chain',
                    'timestamp': format_local_time(row[3]) if row[3] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

            # 5. Check ratings_reviews
            cursor.execute("""
                SELECT review_id, delivery_id, rating, created_at
                FROM public.ratings_reviews
                WHERE bc_rating_tx_hash = %s LIMIT 1
            """, [tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': 'Immutable Rating & Review (public.ratings_reviews)',
                    'record_id': f"Review #{row[0]} · Delivery #{row[1]} (★ {row[2]}/5)",
                    'status': 'Verified On-Chain',
                    'timestamp': format_local_time(row[3]) if row[3] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

            # 6. Check transactions
            cursor.execute("""
                SELECT transaction_id, escrow_id, total_amount, payment_method, status, processed_at
                FROM public.transactions
                WHERE bc_tx_hash = %s LIMIT 1
            """, [tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': 'Financial Transaction (public.transactions)',
                    'record_id': f"TXN #{row[0]} · Escrow #{row[1]} (₱{float(row[2] or 0):,.2f})",
                    'status': f"{row[4]} via {(row[3] or 'GCASH').upper()}",
                    'timestamp': format_local_time(row[5]) if row[5] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

            # 7. Check withdrawal_requests
            cursor.execute("""
                SELECT withdrawal_id, amount, method, status,
                       COALESCE(processed_at, requested_at, updated_at)
                FROM public.withdrawal_requests
                WHERE bc_tx_hash = %s LIMIT 1
            """, [tx_hash])
            row = cursor.fetchone()
            if row:
                return JsonResponse({
                    'found': True,
                    'module': 'Provider Withdrawal (public.withdrawal_requests)',
                    'record_id': f"WDR #{row[0]} (₱{float(row[1] or 0):,.2f})",
                    'status': f"{row[3]} via {(row[2] or 'GCASH').upper()}",
                    'timestamp': format_local_time(row[4]) if row[4] else 'Confirmed',
                    'tx_hash': tx_hash,
                })

        return JsonResponse({'found': False, 'error': 'Hash not found in Pack-N-Ship ledger.'})
    except Exception as e:
        return JsonResponse({'found': False, 'error': str(e)}, status=500)