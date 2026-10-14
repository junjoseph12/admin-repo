# views/vehicle_verification.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from .login import admin_required


@admin_required
def vehicle_verification(request):
    current_tab = request.GET.get('tab', 'pending')
    vehicles = []

    try:
        with connection.cursor() as cursor:
            if current_tab == 'verified':
                status_filter = ['Verified']
            elif current_tab == 'rejected':
                status_filter = ['Rejected']
            else:
                status_filter = ['Pending']

            cursor.execute("""
                SELECT
                    v.vehicle_id, v.vehicle_type, v.plate_number,
                    v.max_volume_liters, v.max_weight_kg,
                    v.cargo_length_cm, v.cargo_width_cm, v.cargo_height_cm,
                    v.vehicle_doc,
                    COALESCE(v.verification_status, 'Pending') AS verification_status,
                    v.provider_id,
                    u.first_name, u.middle_name, u.last_name,
                    u.email, u.phone_number,
                    pv.verification_status AS provider_verif_status
                FROM vehicles v
                JOIN users u ON u.user_id = v.provider_id
                LEFT JOIN provider_verifications pv ON pv.provider_id = u.user_id
                WHERE COALESCE(v.verification_status, 'Pending') = ANY(%s)
                ORDER BY v.vehicle_id DESC
            """, [status_filter])

            for row in cursor.fetchall():
                (vehicle_id, vehicle_type, plate_number,
                 max_volume, max_weight,
                 cargo_length, cargo_width, cargo_height,
                 vehicle_doc, verif_status, provider_id,
                 first_name, middle_name, last_name, email, phone,
                 provider_verif_status) = row

                full_name = " ".join(filter(None, [first_name, middle_name, last_name])) or f"User #{provider_id}"

                vehicles.append({
                    'vehicle_id': vehicle_id,
                    'vehicle_type': vehicle_type or '—',
                    'plate_number': plate_number or '—',
                    'max_volume_liters': float(max_volume) if max_volume is not None else 0,
                    'max_weight_kg': float(max_weight) if max_weight is not None else 0,
                    'cargo_length_cm': float(cargo_length) if cargo_length is not None else 0,
                    'cargo_width_cm': float(cargo_width) if cargo_width is not None else 0,
                    'cargo_height_cm': float(cargo_height) if cargo_height is not None else 0,
                    'vehicle_doc': vehicle_doc or '',
                    'status': verif_status or 'Pending',
                    'provider_id': provider_id,
                    'provider_name': full_name,
                    'provider_email': email or '—',
                    'provider_phone': phone or '—',
                    'provider_verif_status': provider_verif_status or 'Pending',
                })

    except Exception as e:
        print(f"[vehicle_verification] DB error: {e}")

    return render(request, 'pages/vehicle_verification.html', {
        'vehicles': vehicles,
        'current_tab': current_tab,
    })


@admin_required
def approve_vehicle(request, vehicle_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE vehicles SET verification_status = 'Verified' WHERE vehicle_id = %s", [vehicle_id])
            messages.success(request, f'Vehicle #{vehicle_id} approved successfully.')
        except Exception as e:
            print(f"[approve_vehicle] DB error: {e}")
            messages.error(request, f'Failed to approve vehicle: {e}')
    return redirect('vehicle_verification')


@admin_required
def reject_vehicle(request, vehicle_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE vehicles SET verification_status = 'Rejected' WHERE vehicle_id = %s", [vehicle_id])
            messages.success(request, f'Vehicle #{vehicle_id} rejected.')
        except Exception as e:
            print(f"[reject_vehicle] DB error: {e}")
            messages.error(request, f'Failed to reject vehicle: {e}')
    return redirect('vehicle_verification')