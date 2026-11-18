# views/settings.py
from django.shortcuts import render
from django.contrib import messages
from django.db import connection
from .login import admin_required


@admin_required
def settings_page(request):
    settings_data = {
        'door_to_door': '20.00',
        'platform_commission': '8.5',
        'base_fare': '49.00',
        'per_km_rate': '14.50',
    }

    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                new_door_to_door       = request.POST.get('door_to_door', settings_data['door_to_door'])
                new_platform_commission = request.POST.get('platform_commission', settings_data['platform_commission'])
                new_base_fare          = request.POST.get('base_fare', settings_data['base_fare'])
                new_per_km_rate        = request.POST.get('per_km_rate', settings_data['per_km_rate'])

                cursor.execute("SELECT rate_id FROM delivery_rates ORDER BY updated_at DESC LIMIT 1")
                row = cursor.fetchone()

                if row:
                    cursor.execute("""
                        UPDATE delivery_rates
                        SET small_box_fee = %s, base_rate = %s, per_km_rate = %s, updated_at = NOW()
                        WHERE rate_id = %s
                    """, [float(new_door_to_door or 0), float(new_base_fare or 0), float(new_per_km_rate or 0), row[0]])
                else:
                    cursor.execute("""
                        INSERT INTO delivery_rates
                            (delivery_type, small_box_fee, medium_box_fee, large_box_fee, base_rate, per_km_rate, updated_at)
                        VALUES ('Standard', %s, 0, 0, %s, %s, NOW())
                    """, [float(new_door_to_door or 0), float(new_base_fare or 0), float(new_per_km_rate or 0)])

                request.session['platform_commission'] = new_platform_commission
                messages.success(request, 'Settings updated successfully!')

                settings_data = {
                    'door_to_door': new_door_to_door,
                    'platform_commission': new_platform_commission,
                    'base_fare': new_base_fare,
                    'per_km_rate': new_per_km_rate,
                }
                return render(request, 'pages/settings.html', {'settings': settings_data})

            cursor.execute("""
                SELECT small_box_fee, base_rate, per_km_rate, updated_at
                FROM delivery_rates ORDER BY updated_at DESC LIMIT 1
            """)
            row = cursor.fetchone()

            if row:
                settings_data['door_to_door'] = f"{float(row[0] or 0):.2f}"
                settings_data['base_fare']    = f"{float(row[1] or 0):.2f}"
                settings_data['per_km_rate']  = f"{float(row[2] or 0):.2f}"

            settings_data['platform_commission'] = request.session.get(
                'platform_commission', settings_data['platform_commission']
            )

    except Exception as e:
        print(f"[settings_page] DB error: {e}")

    return render(request, 'pages/settings.html', {'settings': settings_data})