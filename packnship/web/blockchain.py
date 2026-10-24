# web/blockchain.py
import os
import json
import time
import hashlib
from datetime import datetime, timezone
from django.db import connection

# Optional Web3 support if you connect Polygon Amoy / Sepolia / Ganache via .env
try:
    from web3 import Web3
except ImportError:
    Web3 = None


def get_network_info():
    """Return active blockchain network metadata for the Admin UI."""
    rpc_url = os.environ.get('BLOCKCHAIN_RPC_URL', '').strip()
    explorer_url = os.environ.get(
        'BLOCKCHAIN_EXPLORER_URL', 'https://amoy.polygonscan.com/tx/'
    ).strip()
    network_name = os.environ.get(
        'BLOCKCHAIN_NETWORK_NAME', 'Polygon Amoy / Pack-N-Ship Anchor'
    ).strip()

    if Web3 and rpc_url:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 4}))
            if w3.is_connected():
                return {
                    'mode': 'live_evm',
                    'network': network_name,
                    'chain_id': w3.eth.chain_id,
                    'block_number': w3.eth.block_number,
                    'explorer_url': explorer_url,
                    'connected': True,
                }
        except Exception as e:
            print(f"[blockchain] RPC connection warning: {e}")

    return {
        'mode': 'cryptographic_ledger',
        'network': f"{network_name} (SHA-256 Ledger)",
        'chain_id': 80002,
        'block_number': None,
        'explorer_url': explorer_url,
        'connected': True,
    }


def anchor_payload_on_chain(event_type: str, payload: dict) -> str:
    """
    Anchors a structured event payload onto EVM (if configured) or generates a
    deterministic cryptographic 0x-prefixed 64-hex SHA-256 transaction hash.
    """
    canonical_record = {
        'app': 'Pack-N-Ship',
        'event': event_type,
        'payload': payload,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'nonce': time.time_ns(),
    }
    serialized = json.dumps(canonical_record, sort_keys=True, default=str)
    digest_hex = '0x' + hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    rpc_url = os.environ.get('BLOCKCHAIN_RPC_URL', '').strip()
    private_key = os.environ.get('BLOCKCHAIN_PRIVATE_KEY', '').strip()

    if Web3 and rpc_url and private_key:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 6}))
            if w3.is_connected():
                account = w3.eth.account.from_key(private_key)
                tx = {
                    'from': account.address,
                    'to': account.address,  # Self-anchor data transaction
                    'value': 0,
                    'gas': 50000,
                    'gasPrice': w3.eth.gas_price,
                    'nonce': w3.eth.get_transaction_count(account.address),
                    'chainId': w3.eth.chain_id,
                    'data': w3.to_bytes(text=f"PNS:{event_type}:{digest_hex}"),
                }
                signed = w3.eth.account.sign_transaction(tx, private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                hex_hash = tx_hash.hex()
                return hex_hash if hex_hash.startswith('0x') else f"0x{hex_hash}"
        except Exception as e:
            print(f"[blockchain] Live EVM broadcast fallback to SHA-256 anchor: {e}")

    return digest_hex


# ==============================================================================
# SCHEMA-SPECIFIC ANCHORING HELPERS
# ==============================================================================

def anchor_provider_verification(cursor, user_id: int, license_no: str = '') -> str:
    """Anchors a provider KYC verification and updates provider_verifications.bc_verif_tx_hash."""
    tx_hash = anchor_payload_on_chain(
        'PROVIDER_VERIFIED',
        {
            'provider_id': int(user_id),
            'drivers_license_number': str(license_no or ''),
            'status': 'Approved',
        },
    )
    cursor.execute("""
        UPDATE public.provider_verifications
        SET bc_verif_tx_hash = %s
        WHERE provider_id = %s
    """, [tx_hash, user_id])
    return tx_hash


def anchor_escrow_payment(cursor, escrow_id: int) -> str:
    """Anchors an escrow payment record and updates escrow_payments.bc_escrow_tx_hash."""
    cursor.execute("""
        SELECT escrow_id, delivery_id, sender_id, provider_id, amount, escrow_status
        FROM public.escrow_payments
        WHERE escrow_id = %s
    """, [escrow_id])
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Escrow #{escrow_id} not found.")

    eid, delivery_id, sender_id, provider_id, amount, escrow_status = row
    tx_hash = anchor_payload_on_chain(
        'ESCROW_ANCHOR',
        {
            'escrow_id': eid,
            'delivery_id': delivery_id,
            'sender_id': sender_id,
            'provider_id': provider_id,
            'amount': str(amount),
            'escrow_status': escrow_status,
        },
    )
    cursor.execute("""
        UPDATE public.escrow_payments
        SET bc_escrow_tx_hash = %s
        WHERE escrow_id = %s
    """, [tx_hash, eid])
    return tx_hash


def anchor_delivery_log(cursor, delivery_id: int) -> str:
    """Anchors a delivery record into public.blockchain_logs."""
    cursor.execute("""
        SELECT d.delivery_id, d.request_id, d.provider_id, d.vehicle_id,
               d.accepted_at, d.completed_at
        FROM public.deliveries d
        WHERE d.delivery_id = %s
    """, [delivery_id])
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Delivery #{delivery_id} not found.")

    did, req_id, prov_id, veh_id, accepted_at, completed_at = row
    tx_hash = anchor_payload_on_chain(
        'DELIVERY_AUDIT_LOG',
        {
            'delivery_id': did,
            'request_id': req_id,
            'provider_id': prov_id,
            'vehicle_id': veh_id,
            'accepted_at': str(accepted_at),
            'completed_at': str(completed_at),
        },
    )
    cursor.execute("""
        INSERT INTO public.blockchain_logs (delivery_id, tx_hash, status, created_at)
        VALUES (%s, %s, 'confirmed', NOW())
        ON CONFLICT (tx_hash) DO NOTHING
    """, [did, tx_hash])
    return tx_hash


def anchor_qr_handoff(cursor, qr_id: int, handoff_type: str = 'pickup') -> str:
    """Anchors a QR pickup or dropoff verification hash in public.qr_verifications."""
    cursor.execute("""
        SELECT qr_id, delivery_id, pickup_qr, dropoff_qr, pickup_verified, dropoff_verified
        FROM public.qr_verifications
        WHERE qr_id = %s
    """, [qr_id])
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"QR Verification #{qr_id} not found.")

    qid, delivery_id, pickup_qr, dropoff_qr, p_ver, d_ver = row
    is_dropoff = (handoff_type or '').lower() == 'dropoff'

    tx_hash = anchor_payload_on_chain(
        'QR_DROPOFF_VERIFIED' if is_dropoff else 'QR_PICKUP_VERIFIED',
        {
            'qr_id': qid,
            'delivery_id': delivery_id,
            'qr_token': dropoff_qr if is_dropoff else pickup_qr,
            'verified': bool(d_ver if is_dropoff else p_ver),
        },
    )
    if is_dropoff:
        cursor.execute("""
            UPDATE public.qr_verifications
            SET bc_dropoff_tx_hash = %s
            WHERE qr_id = %s
        """, [tx_hash, qid])
    else:
        cursor.execute("""
            UPDATE public.qr_verifications
            SET bc_pickup_tx_hash = %s
            WHERE qr_id = %s
        """, [tx_hash, qid])
    return tx_hash


def anchor_rating_review(cursor, review_id: int) -> str:
    """Anchors a rating & review record in public.ratings_reviews."""
    cursor.execute("""
        SELECT review_id, delivery_id, reviewer_id, reviewee_id, rating, review_text
        FROM public.ratings_reviews
        WHERE review_id = %s
    """, [review_id])
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Review #{review_id} not found.")

    rid, delivery_id, reviewer_id, reviewee_id, rating, review_text = row
    tx_hash = anchor_payload_on_chain(
        'RATING_REVIEW_ANCHOR',
        {
            'review_id': rid,
            'delivery_id': delivery_id,
            'reviewer_id': reviewer_id,
            'reviewee_id': reviewee_id,
            'rating': rating,
            'review_sha256': hashlib.sha256((review_text or '').encode('utf-8')).hexdigest(),
        },
    )
    cursor.execute("""
        UPDATE public.ratings_reviews
        SET bc_rating_tx_hash = %s
        WHERE review_id = %s
    """, [tx_hash, rid])
    return tx_hash

def anchor_financial_transaction(cursor, transaction_id: int) -> str:
    """Anchors a financial transaction record."""
    cursor.execute("""
        SELECT transaction_id, escrow_id, total_amount, payment_method, status
        FROM public.transactions
        WHERE transaction_id = %s
    """, [transaction_id])
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Transaction #{transaction_id} not found.")

    tid, escrow_id, amount, method, status = row
    tx_hash = anchor_payload_on_chain(
        'FINANCIAL_TRANSACTION',
        {
            'transaction_id': tid,
            'escrow_id': escrow_id,
            'amount': str(amount),
            'method': method,
            'status': status,
        },
    )
    cursor.execute("""
        UPDATE public.transactions
        SET bc_tx_hash = %s
        WHERE transaction_id = %s
    """, [tx_hash, tid])
    return tx_hash

def anchor_withdrawal(cursor, withdrawal_id: int) -> str:
    """Anchors a provider withdrawal request."""
    cursor.execute("""
        SELECT withdrawal_id, provider_wallet_id, amount, method, status
        FROM public.withdrawal_requests
        WHERE withdrawal_id = %s
    """, [withdrawal_id])
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Withdrawal #{withdrawal_id} not found.")

    wid, wallet_id, amount, method, status = row
    tx_hash = anchor_payload_on_chain(
        'WITHDRAWAL_REQUEST',
        {
            'withdrawal_id': wid,
            'wallet_id': wallet_id,
            'amount': str(amount),
            'method': method,
            'status': status,
        },
    )
    cursor.execute("""
        UPDATE public.withdrawal_requests
        SET bc_tx_hash = %s
        WHERE withdrawal_id = %s
    """, [tx_hash, wid])
    return tx_hash