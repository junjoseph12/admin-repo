# views/provider_verification.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from .login import admin_required


@admin_required
def provider_verification(request):
    current_tab = request.GET.get('tab', 'pending')
    verifications = []

    try:
        with connection.cursor() as cursor:
            status_filter = ['Rejected'] if current_tab == 'rejected' else ['Pending']

            cursor.execute("""
                SELECT
                    pv.verification_id, pv.drivers_license_number, pv.license_expiry_date,
                    pv.selfie_photo, pv.selfie_photo_back,
                    pv.id_analyzer_decision, pv.id_analyzer_confidence, pv.id_analyzer_raw,
                    COALESCE(pv.verification_status, 'Pending') AS verification_status,
                    pv.submitted_at, pv.bc_verif_tx_hash,
                    u.user_id, u.first_name, u.middle_name, u.last_name,
                    u.email, u.phone_number, u.id_photo, u.valid_id_type, u.valid_id_number,
                    v.vehicle_type, v.plate_number, v.vehicle_doc,
                    v.verification_status AS vehicle_verif_status
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.user_id
                JOIN roles r       ON r.role_id   = ur.role_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                LEFT JOIN vehicles v ON v.provider_id = u.user_id
                WHERE r.role_name ILIKE 'provider'
                  AND COALESCE(pv.verification_status, 'Pending') = ANY(%s)
                ORDER BY COALESCE(pv.submitted_at, u.created_at) DESC
            """, [status_filter])

            for row in cursor.fetchall():
                (verification_id, license_no, expiry_date, selfie_photo, selfie_photo_back,
                 id_analyzer_decision, id_analyzer_confidence, id_analyzer_raw,
                 verif_status, submitted_at, tx_hash,
                 uid, first_name, middle_name, last_name, email, phone,
                 id_photo, valid_id_type, valid_id_number,
                 vehicle_type, plate_number, vehicle_doc, vehicle_verif_status) = row

                full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{uid}"

                verifications.append({
                    'verification_id': verification_id or 0,
                    'user_id': uid,
                    'name': full_name,
                    'email': email or '—',
                    'phone': phone or '—',
                    'license_no': license_no or '—',
                    'license_expiry': expiry_date.strftime('%Y-%m-%d') if expiry_date else '—',
                    'selfie_photo': selfie_photo or '',
                    'selfie_photo_back': selfie_photo_back or '',
                    'id_analyzer_decision': id_analyzer_decision or '',
                    'id_analyzer_confidence': float(id_analyzer_confidence) if id_analyzer_confidence is not None else None,
                    'id_analyzer_raw': id_analyzer_raw or {},
                    'id_photo': id_photo or '',
                    'valid_id_type': valid_id_type or '—',
                    'valid_id_number': valid_id_number or '—',
                    'vehicle_type': vehicle_type or '—',
                    'plate_no': plate_number or '—',
                    'vehicle_doc': vehicle_doc or '',
                    'vehicle_verif_status': vehicle_verif_status or 'Pending',
                    'status': verif_status or 'Pending',
                    'submitted_at': submitted_at.strftime('%b %d, %Y %I:%M %p') if submitted_at else '—',
                    'bc_verif_tx_hash': tx_hash or '',
                })

    except Exception as e:
        print(f"[provider_verification] DB error: {e}")

    return render(request, 'pages/provider_verification.html', {
        'verifications': verifications,
        'current_tab': current_tab,
    })


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
                        SET verification_status = 'Approved', verified_at = NOW()
                        WHERE provider_id = %s
                    """, [user_id])
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, verified_at, provider_id)
                        VALUES (%s, NOW()::date, 'N/A', 'Approved', NOW(), %s)
                    """, [placeholder_license, user_id])

                cursor.execute("UPDATE users SET is_verified = TRUE WHERE user_id = %s", [user_id])

            messages.success(request, f'Provider (US{user_id}) approved successfully.')
        except Exception as e:
            print(f"[approve_provider] DB error: {e}")
            messages.error(request, f'Failed to approve provider: {e}')

    return redirect('provider_verification')


@admin_required
def reject_provider(request, user_id):
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
                        SET verification_status = 'Rejected'
                        WHERE provider_id = %s
                    """, [user_id])
                else:
                    placeholder_license = f"PENDING-{user_id}"
                    cursor.execute("""
                        INSERT INTO provider_verifications
                            (drivers_license_number, license_expiry_date, selfie_photo,
                             verification_status, provider_id)
                        VALUES (%s, NOW()::date, 'N/A', 'Rejected', %s)
                    """, [placeholder_license, user_id])

                cursor.execute("UPDATE users SET is_verified = FALSE WHERE user_id = %s", [user_id])

            messages.success(request, f'Provider (US{user_id}) rejected.')
        except Exception as e:
            print(f"[reject_provider] DB error: {e}")
            messages.error(request, f'Failed to reject provider: {e}')

    return redirect('provider_verification')