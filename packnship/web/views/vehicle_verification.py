# views/vehicle_verification.py
import os

from django.contrib import messages
from django.db import IntegrityError, connection, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from .utils import log_admin_action 
from .login import admin_required
from ..supabase_storage import StorageError, create_signed_url, parse_storage_ref


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
                    u.first_name, u.last_name,
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
                 first_name, last_name, email, phone,
                 provider_verif_status) = row

                # Updated: removed middle_name from full_name construction
                full_name = " ".join(filter(None, [first_name, last_name])) or f"User #{provider_id}"

                vehicles.append({
                    'vehicle_id': vehicle_id,
                    'vehicle_type': vehicle_type or '—',
                    'plate_number': plate_number or '—',
                    'max_volume_liters': float(max_volume) if max_volume is not None else 0,
                    'max_weight_kg': float(max_weight) if max_weight is not None else 0,
                    'cargo_length_cm': float(cargo_length) if cargo_length is not None else 0,
                    'cargo_width_cm': float(cargo_width) if cargo_width is not None else 0,
                    'cargo_height_cm': float(cargo_height) if cargo_height is not None else 0,
                    # The raw storage link no longer goes to the browser.
                    # The page gets an admin-only URL that makes a short-lived link on click.
                    'has_doc': bool(vehicle_doc),
                    'doc_url': reverse('vehicle_document', args=[vehicle_id]) if vehicle_doc else '',
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
def vehicle_document(request, vehicle_id):
    """Redirect an admin to a 2-minute signed link for the vehicle's OR/CR file."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT vehicle_doc FROM vehicles WHERE vehicle_id = %s", [vehicle_id])
            row = cursor.fetchone()
    except Exception as e:
        print(f"[vehicle_document] DB error: {e}")
        messages.error(request, 'Could not load the document.')
        return redirect('vehicle_verification')

    if not row or not row[0]:
        raise Http404('No document uploaded.')

    try:
        bucket, path = parse_storage_ref(
            row[0], default_bucket=os.environ.get('SUPABASE_VEHICLE_DOCS_BUCKET')
        )
        url = create_signed_url(bucket, path, expires_in=120)
    except StorageError as e:
        print(f"[vehicle_document] storage error for vehicle {vehicle_id}: {e}")
        messages.error(request, f'Could not open the document: {e}')
        return redirect('vehicle_verification')

    response = redirect(url)
    response['Cache-Control'] = 'no-store'
    return response

@admin_required
def approve_vehicle(request, vehicle_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE vehicles SET verification_status = 'Verified' WHERE vehicle_id = %s", [vehicle_id])
            
            messages.success(request, f'Vehicle #{vehicle_id} approved successfully.')
            # ✅ Log action
            log_admin_action(request, f"Approved Vehicle Verification for Vehicle #{vehicle_id}")
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
            # ✅ Log action
            log_admin_action(request, f"Rejected Vehicle Verification for Vehicle #{vehicle_id}")
        except Exception as e:
            print(f"[reject_vehicle] DB error: {e}")
            messages.error(request, f'Failed to reject vehicle: {e}')
    return redirect('vehicle_verification')


def _back_to_tab(request):
    """Return to the tab the admin was on (only known tabs are accepted)."""
    tab = request.POST.get('tab') or 'verified'
    if tab not in ('pending', 'verified', 'rejected'):
        tab = 'verified'
    return redirect(f"{reverse('vehicle_verification')}?tab={tab}")


def _positive_number(raw, label):
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a number.')
    if value <= 0:
        raise ValueError(f'{label} must be greater than 0.')
    return value


@admin_required
def edit_vehicle(request, vehicle_id):
    """Admin edit of a vehicle's details. The verification status is NOT changed."""
    if request.method != 'POST':
        return redirect('vehicle_verification')

    try:
        vehicle_type = (request.POST.get('vehicle_type') or '').strip()
        plate = (request.POST.get('plate_number') or '').strip().upper()
        if not vehicle_type:
            raise ValueError('Vehicle type is required.')
        if not plate:
            raise ValueError('Plate number is required.')

        volume = _positive_number(request.POST.get('max_volume_liters'), 'Max volume')
        weight = _positive_number(request.POST.get('max_weight_kg'), 'Max weight')
        length = _positive_number(request.POST.get('cargo_length_cm'), 'Cargo length')
        width = _positive_number(request.POST.get('cargo_width_cm'), 'Cargo width')
        height = _positive_number(request.POST.get('cargo_height_cm'), 'Cargo height')

        with connection.cursor() as cursor:
            cursor.execute("SELECT plate_number FROM vehicles WHERE vehicle_id = %s", [vehicle_id])
            existing = cursor.fetchone()
            if not existing:
                messages.error(request, f'Vehicle #{vehicle_id} was not found.')
                return _back_to_tab(request)

            cursor.execute("""
                UPDATE vehicles
                   SET vehicle_type = %s, plate_number = %s,
                       max_volume_liters = %s, max_weight_kg = %s,
                       cargo_length_cm = %s, cargo_width_cm = %s, cargo_height_cm = %s
                 WHERE vehicle_id = %s
            """, [vehicle_type, plate, volume, weight, length, width, height, vehicle_id])

        messages.success(request, f'Vehicle #{vehicle_id} updated.')
        log_admin_action(request, f"Edited Vehicle #{vehicle_id} ({existing[0]} -> {plate})")
    except ValueError as e:
        messages.error(request, str(e))
    except IntegrityError:
        messages.error(request, 'That plate number is already registered to another vehicle.')
    except Exception as e:
        print(f"[edit_vehicle] DB error: {e}")
        messages.error(request, f'Failed to update vehicle: {e}')
    return _back_to_tab(request)


@admin_required
def delete_vehicle(request, vehicle_id):
    """
    Delete a vehicle. A vehicle that has delivery history is kept (the records must stay intact).
    Otherwise its routes and their open matches are removed with it, all in one transaction.
    """
    if request.method != 'POST':
        return redirect('vehicle_verification')

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT plate_number FROM vehicles WHERE vehicle_id = %s FOR UPDATE", [vehicle_id]
                )
                row = cursor.fetchone()
                if not row:
                    messages.error(request, f'Vehicle #{vehicle_id} was not found.')
                    return _back_to_tab(request)
                plate = row[0]

                cursor.execute("SELECT route_id FROM provider_routes WHERE vehicle_id = %s", [vehicle_id])
                route_ids = [r[0] for r in cursor.fetchall()]

                cursor.execute(
                    "SELECT COUNT(*) FROM deliveries WHERE vehicle_id = %s OR route_id = ANY(%s)",
                    [vehicle_id, route_ids],
                )
                delivery_count = cursor.fetchone()[0]
                if delivery_count:
                    messages.error(
                        request,
                        f'{plate} cannot be deleted: it has {delivery_count} delivery record(s). '
                        'Delivery history must be kept.'
                    )
                    return _back_to_tab(request)

                if route_ids:
                    cursor.execute("DELETE FROM route_request_matches WHERE route_id = ANY(%s)", [route_ids])
                    cursor.execute(
                        "UPDATE delivery_requests SET preferred_route_id = NULL WHERE preferred_route_id = ANY(%s)",
                        [route_ids],
                    )
                    cursor.execute(
                        "UPDATE provider_live_locations SET route_id = NULL WHERE route_id = ANY(%s)", [route_ids]
                    )
                    cursor.execute("DELETE FROM provider_routes WHERE route_id = ANY(%s)", [route_ids])

                cursor.execute("DELETE FROM vehicles WHERE vehicle_id = %s", [vehicle_id])

        extra = f' and {len(route_ids)} route(s)' if route_ids else ''
        messages.success(request, f'Vehicle {plate} deleted{extra}.')
        log_admin_action(request, f"Deleted Vehicle #{vehicle_id} ({plate}){extra}")
    except Exception as e:
        print(f"[delete_vehicle] DB error: {e}")
        messages.error(request, f'Failed to delete vehicle: {e}')
    return _back_to_tab(request)