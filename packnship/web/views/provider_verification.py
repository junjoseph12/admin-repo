# views/provider_verification.py
import os

from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection, transaction
from django.http import Http404
from django.urls import reverse
from .login import admin_required
from .utils import log_admin_action
from ..supabase_storage import StorageError, create_signed_url, parse_storage_ref

# Which stored photo each URL kind points to. Fixed SQL, nothing from the request goes into it.
PHOTO_QUERIES = {
    'front':  "SELECT selfie_photo FROM provider_verifications WHERE provider_id = %s ORDER BY submitted_at DESC LIMIT 1",
    'back':   "SELECT selfie_photo_back FROM provider_verifications WHERE provider_id = %s ORDER BY submitted_at DESC LIMIT 1",
    'selfie': "SELECT live_selfie_photo FROM provider_verifications WHERE provider_id = %s ORDER BY submitted_at DESC LIMIT 1",
    'id':     "SELECT id_photo FROM users WHERE user_id = %s",
}


def _photo_url(user_id, kind, stored_value):
    """Admin-only URL for a photo, or '' if nothing real is stored ('N/A' is a placeholder)."""
    if not stored_value or str(stored_value).strip().upper() == 'N/A':
        return ''
    return reverse('provider_photo', args=[user_id, kind])


def _confidence_pct(raw):
    """
    Normalize the ID Analyzer confidence to a 0-100 percentage.

    provider_verifications.id_analyzer_confidence is a plain `numeric`. Depending on what the
    mobile app / ID Analyzer wrote, it can be a ratio (0.96) or already a percentage (96.00).
    The old template always multiplied by 100, so 96.00 showed up as 9600%.
      - value <= 1  -> treated as a ratio, scaled to a percentage (0.96 -> 96.00)
      - value  > 1  -> already a percentage, left alone     (96.00 -> 96.00)
    """
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 1:
        value *= 100
    return round(min(max(value, 0.0), 100.0), 2)


@admin_required
def provider_verification(request):
    current_tab = request.GET.get('tab', 'pending')
    verifications = []

    try:
        with connection.cursor() as cursor:
            status_filter = ['Rejected'] if current_tab == 'rejected' else ['Pending']

            # All columns below exist in the schema (live_selfie_photo and rejection_reason included),
            # so the old per-request ALTER TABLE / information_schema checks are gone.
            # The vehicle is a LATERAL "latest vehicle" so a provider with several vehicles
            # no longer appears as several duplicate rows.
            cursor.execute("""
                SELECT
                    pv.verification_id, pv.drivers_license_number, pv.license_expiry_date,
                    pv.selfie_photo, pv.selfie_photo_back, pv.live_selfie_photo,
                    pv.id_analyzer_decision, pv.id_analyzer_confidence, pv.id_analyzer_raw,
                    COALESCE(pv.verification_status, 'Pending') AS verification_status,
                    pv.submitted_at, pv.bc_verif_tx_hash,
                    pv.rejection_reason,
                    u.user_id, u.first_name, u.last_name,
                    u.email, u.phone_number, u.id_photo, u.valid_id_type, u.valid_id_number,
                    v.vehicle_type, v.plate_number, v.vehicle_doc,
                    v.verification_status AS vehicle_verif_status
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.user_id
                JOIN roles r       ON r.role_id   = ur.role_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                LEFT JOIN LATERAL (
                    SELECT vehicle_type, plate_number, vehicle_doc, verification_status
                    FROM vehicles
                    WHERE provider_id = u.user_id
                    ORDER BY vehicle_id DESC
                    LIMIT 1
                ) v ON TRUE
                WHERE r.role_name ILIKE 'provider'
                  AND COALESCE(pv.verification_status, 'Pending') = ANY(%s)
                ORDER BY COALESCE(pv.submitted_at, u.created_at) DESC
            """, [status_filter])

            for row in cursor.fetchall():
                (verification_id, license_no, expiry_date, selfie_photo, selfie_photo_back,
                 live_selfie_photo,
                 id_analyzer_decision, id_analyzer_confidence, id_analyzer_raw,
                 verif_status, submitted_at, tx_hash,
                 rejection_reason,
                 uid, first_name, last_name, email, phone,
                 id_photo, valid_id_type, valid_id_number,
                 vehicle_type, plate_number, vehicle_doc, vehicle_verif_status) = row

                full_name = " ".join(filter(None, [first_name, last_name])) or f"User #{uid}"
                confidence_pct = _confidence_pct(id_analyzer_confidence)

                verifications.append({
                    'verification_id': verification_id or 0,
                    'user_id': uid,
                    'name': full_name,
                    'email': email or '—',
                    'phone': phone or '—',
                    'license_no': license_no or '—',
                    'license_expiry': expiry_date.strftime('%Y-%m-%d') if expiry_date else '—',
                    'selfie_photo': _photo_url(uid, 'front', selfie_photo),
                    'selfie_photo_back': _photo_url(uid, 'back', selfie_photo_back),
                    'live_selfie_photo': _photo_url(uid, 'selfie', live_selfie_photo),
                    'id_analyzer_decision': id_analyzer_decision or '',
                    # Always a 0-100 number (or None) -> the template just appends "%".
                    'id_analyzer_confidence': confidence_pct,
                    'id_analyzer_confidence_display': f"{confidence_pct:.2f}%" if confidence_pct is not None else '',
                    'id_analyzer_raw': id_analyzer_raw or {},
                    'id_photo': _photo_url(uid, 'id', id_photo),
                    'valid_id_type': valid_id_type or '—',
                    'valid_id_number': valid_id_number or '—',
                    'vehicle_type': vehicle_type or '—',
                    'plate_no': plate_number or '—',
                    'vehicle_verif_status': vehicle_verif_status or 'Pending',
                    'status': verif_status or 'Pending',
                    'rejection_reason': rejection_reason or '',
                    'submitted_at': submitted_at.strftime('%b %d, %Y %I:%M %p') if submitted_at else '—',
                    'bc_verif_tx_hash': tx_hash or '',
                })

    except Exception as e:
        print(f"[provider_verification] DB error: {e}")

    return render(request, 'pages/provider_verification.html', {
        'verifications': verifications,
        'current_tab': current_tab,
    })


def _anchor_approved_provider(cursor, user_id):
    """
    Anchor the KYC approval on-chain right away (no need to wait for a manual sync).
    Never lets a blockchain problem undo or block the approval itself: the work runs in a
    savepoint and any error is only logged. Anything that fails here is picked up later by
    the background auto-anchor job.
    """
    try:
        from ..blockchain import anchor_provider_verification
        cursor.execute("""
            SELECT drivers_license_number, bc_verif_tx_hash
            FROM provider_verifications
            WHERE provider_id = %s
        """, [user_id])
        row = cursor.fetchone()
        if not row or (row[1] or '').strip():
            return  # nothing to anchor, or it is already anchored
        with transaction.atomic():
            anchor_provider_verification(cursor, user_id, row[0])
    except Exception as e:
        print(f"[approve_provider] auto-anchor skipped for US{user_id}: {e}")


@admin_required
def approve_provider(request, user_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT verification_id FROM provider_verifications
                    WHERE provider_id = %s
                    ORDER BY submitted_at DESC LIMIT 1
                """, [user_id])
                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE provider_verifications
                        SET verification_status = 'Approved',
                            verified_at = NOW(),
                            rejection_reason = NULL
                        WHERE provider_id = %s
                    """, [user_id])
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, verified_at, provider_id, rejection_reason)
                        VALUES (%s, NOW()::date, 'N/A', 'Approved', NOW(), %s, NULL)
                    """, [placeholder_license, user_id])

                cursor.execute("UPDATE users SET is_verified = TRUE WHERE user_id = %s", [user_id])

                # In-app notification for approval
                cursor.execute("""
                    INSERT INTO notification_log (user_id, title, body, type, is_read)
                    VALUES (%s, %s, %s, %s, false)
                """, [
                    user_id,
                    'Provider Application Approved',
                    'Congratulations! Your provider application has been approved. You can now switch to Provider Mode.',
                    'provider_verification',
                ])

                # Record the approval on the blockchain immediately.
                _anchor_approved_provider(cursor, user_id)

            messages.success(request, f'Provider (US{user_id}) approved successfully.')
            log_admin_action(request, f"Approved Provider Verification for User US{user_id}")
        except Exception as e:
            print(f"[approve_provider] DB error: {e}")
            messages.error(request, f'Failed to approve provider: {e}')

    return redirect('provider_verification')


@admin_required
def reject_provider(request, user_id):
    if request.method == 'POST':
        rejection_reason = (request.POST.get('rejection_reason') or '').strip()
        if not rejection_reason:
            messages.error(request, 'Please provide a reason for rejecting this provider application.')
            return redirect('provider_verification')

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT verification_id FROM provider_verifications
                    WHERE provider_id = %s
                    ORDER BY submitted_at DESC LIMIT 1
                """, [user_id])
                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE provider_verifications
                        SET verification_status = 'Rejected',
                            rejection_reason = %s
                        WHERE provider_id = %s
                    """, [rejection_reason, user_id])
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, provider_id, rejection_reason)
                        VALUES (%s, NOW()::date, 'N/A', 'Rejected', %s, %s)
                    """, [placeholder_license, user_id, rejection_reason])

                cursor.execute("UPDATE users SET is_verified = FALSE WHERE user_id = %s", [user_id])

                # Also log an in-app notification with the rejection reason
                cursor.execute("""
                    INSERT INTO notification_log (user_id, title, body, type, is_read)
                    VALUES (%s, %s, %s, %s, false)
                """, [
                    user_id,
                    'Provider Application Rejected',
                    f'Your provider application was rejected. Reason: {rejection_reason}',
                    'provider_verification',
                ])

            messages.success(request, f'Provider (US{user_id}) rejected.')
            log_admin_action(request, f"Rejected Provider Verification for User US{user_id} (Reason: {rejection_reason})")
        except Exception as e:
            print(f"[reject_provider] DB error: {e}")
            messages.error(request, f'Failed to reject provider: {e}')

    return redirect('provider_verification')


@admin_required
def provider_photo(request, user_id, kind):
    """Redirect an admin to a 2-minute signed link for one provider photo."""
    sql = PHOTO_QUERIES.get(kind)
    if not sql:
        raise Http404('Unknown photo type.')

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, [user_id])
            row = cursor.fetchone()
    except Exception as e:
        print(f"[provider_photo] DB error: {e}")
        raise Http404('Photo not available.')

    if not row or not row[0] or str(row[0]).strip().upper() == 'N/A':
        raise Http404('No photo on file.')

    try:
        bucket, path = parse_storage_ref(
            row[0], default_bucket=os.environ.get('SUPABASE_VEHICLE_DOCS_BUCKET')
        )
        url = create_signed_url(bucket, path, expires_in=120)
    except StorageError as e:
        print(f"[provider_photo] storage error for user {user_id} ({kind}): {e}")
        raise Http404('Photo not available.')

    response = redirect(url)
    response['Cache-Control'] = 'no-store'
    return response