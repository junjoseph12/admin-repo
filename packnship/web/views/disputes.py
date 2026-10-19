# views/disputes.py
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse
from django.contrib import messages
from django.db import connection
import json
from .login import admin_required


# ==========================================
# MANAGE DISPUTES (admin list + detail modal)
# ==========================================
@admin_required
def admin_disputes_view(request):
    """
    Renders the disputes page. Data is loaded via AJAX from
    `disputes_list_api` so the table can filter by tab (open / resolved / dismissed).
    """
    current_tab = request.GET.get('tab', 'open')
    return render(request, 'pages/admin_disputes.html', {'current_tab': current_tab})


@admin_required
@require_http_methods(["GET"])
def disputes_list_api(request):
    """
    Returns a list of disputes filtered by status tab.
    Tabs: 'open' (Awaiting Provider + Under Review), 'resolved', 'dismissed'.
    """
    tab = request.GET.get('tab', 'open')
    search = (request.GET.get('q') or '').strip()

    tab_status_map = {
        'open':      ('Awaiting Provider', 'Under Review'),
        'resolved':  ('Resolved',),
        'dismissed': ('Dismissed',),
    }
    statuses = tab_status_map.get(tab, tab_status_map['open'])

    sql = """
        SELECT
            d.dispute_id,
            d.dispute_ref,
            d.request_id,
            d.issue_type,
            d.description,
            d.status,
            d.created_at,
            d.resolved_at,
            d.provider_response,
            d.provider_responded_at,
            d.resolution,
            d.reported_by,
            d.provider_id,
            rep.first_name  AS rep_first,
            rep.last_name   AS rep_last,
            prov.first_name AS prov_first,
            prov.last_name  AS prov_last
        FROM disputes d
        LEFT JOIN users rep  ON rep.user_id  = d.reported_by
        LEFT JOIN users prov ON prov.user_id = d.provider_id
        WHERE d.status = ANY(%s)
    """
    params = [list(statuses)]

    if search:
        sql += """
          AND (
            d.dispute_ref ILIKE %s
            OR d.issue_type ILIKE %s
            OR d.description ILIKE %s
            OR CAST(d.request_id AS TEXT) ILIKE %s
            OR CAST(d.dispute_id AS TEXT) ILIKE %s
          )
        """
        like = f"%{search}%"
        params.extend([like] * 5)

    sql += " ORDER BY d.created_at DESC LIMIT 300"

    disputes = []
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                (dispute_id, dispute_ref, request_id, issue_type, description,
                 status, created_at, resolved_at, provider_response,
                 provider_responded_at, resolution, reported_by, provider_id,
                 rep_first, rep_last, prov_first, prov_last) = row

                reporter_name  = f"{rep_first or ''} {rep_last or ''}".strip()  or f"USR-{reported_by}"
                provider_name  = f"{prov_first or ''} {prov_last or ''}".strip() or f"USR-{provider_id}"

                disputes.append({
                    'dispute_id': dispute_id,
                    'dispute_ref': dispute_ref or f"Case #{dispute_id}",
                    'request_id': request_id,
                    'tracking_id': f"PNS-{int(request_id):04d}" if request_id else '—',
                    'issue_type': issue_type or 'Other',
                    'description': description or '',
                    'status': status or 'Awaiting Provider',
                    'created_at': created_at.isoformat() if created_at else None,
                    'resolved_at': resolved_at.isoformat() if resolved_at else None,
                    'provider_response': provider_response or '',
                    'provider_responded_at': provider_responded_at.isoformat() if provider_responded_at else None,
                    'resolution': resolution or '',
                    'reported_by': reported_by,
                    'provider_id': provider_id,
                    'reporter_name': reporter_name,
                    'provider_name': provider_name,
                })
    except Exception as e:
        print(f"[disputes_list_api] DB error: {e}")

    return JsonResponse({'disputes': disputes, 'tab': tab})


@admin_required
@require_http_methods(["GET"])
def dispute_detail_api(request, dispute_id):
    """
    Full details for the modal, including chain of events.
    """
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT
                    d.dispute_id, d.dispute_ref, d.request_id, d.issue_type,
                    d.description, d.status, d.created_at, d.resolved_at,
                    d.provider_response, d.provider_responded_at, d.resolution,
                    d.reported_by, d.provider_id,
                    rep.first_name, rep.last_name, rep.email, rep.phone_number,
                    prov.first_name, prov.last_name, prov.email, prov.phone_number
                FROM disputes d
                LEFT JOIN users rep  ON rep.user_id  = d.reported_by
                LEFT JOIN users prov ON prov.user_id = d.provider_id
                WHERE d.dispute_id = %s
            """, [dispute_id])
            row = cur.fetchone()

            if not row:
                return JsonResponse({'error': 'Dispute not found'}, status=404)

            (did, dref, rid, issue_type, description, status, created_at, resolved_at,
             provider_response, provider_responded_at, resolution,
             reported_by, provider_id,
             rep_first, rep_last, rep_email, rep_phone,
             prov_first, prov_last, prov_email, prov_phone) = row

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'dispute': {
            'dispute_id': did,
            'dispute_ref': dref or f"Case #{did}",
            'request_id': rid,
            'tracking_id': f"PNS-{int(rid):04d}" if rid else '—',
            'issue_type': issue_type or 'Other',
            'description': description or '',
            'status': status,
            'created_at': created_at.isoformat() if created_at else None,
            'resolved_at': resolved_at.isoformat() if resolved_at else None,
            'provider_response': provider_response or '',
            'provider_responded_at': provider_responded_at.isoformat() if provider_responded_at else None,
            'resolution': resolution or '',
            'reporter': {
                'user_id': reported_by,
                'name': f"{rep_first or ''} {rep_last or ''}".strip() or f"USR-{reported_by}",
                'email': rep_email or '—',
                'phone': rep_phone or '—',
            },
            'provider': {
                'user_id': provider_id,
                'name': f"{prov_first or ''} {prov_last or ''}".strip() or f"USR-{provider_id}",
                'email': prov_email or '—',
                'phone': prov_phone or '—',
            },
        }
    })


@admin_required
@require_POST
def dispute_resolve_api(request, dispute_id):
    """
    Admin marks a dispute as Resolved with a resolution note.
    Body: { "resolution": "..." }
    """
    try:
        body = json.loads(request.body)
    except Exception:
        body = {}

    resolution = (body.get('resolution') or '').strip()
    if len(resolution) < 5:
        return JsonResponse({'error': 'Resolution note is required (min 5 chars).'}, status=400)

    try:
        with connection.cursor() as cur:
            cur.execute("""
                UPDATE disputes
                SET status = 'Resolved',
                    resolution = %s,
                    resolved_at = NOW()
                WHERE dispute_id = %s
                RETURNING dispute_id
            """, [resolution, dispute_id])
            updated = cur.fetchone()
            if not updated:
                return JsonResponse({'error': 'Dispute not found'}, status=404)

            # Optional: notify reporter + provider
            cur.execute("""
                SELECT reported_by, provider_id, dispute_ref, request_id
                FROM disputes WHERE dispute_id = %s
            """, [dispute_id])
            rep_id, prov_id, dref, rid = cur.fetchone()

            note_title = f"Dispute {dref or ('#' + str(dispute_id))} resolved"
            note_body  = resolution[:140]

            for target in (rep_id, prov_id):
                if target:
                    cur.execute("""
                        INSERT INTO notification_log (user_id, title, body, type, ref_id)
                        VALUES (%s, %s, %s, 'dispute', %s)
                    """, [target, note_title, note_body, dispute_id])
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'status': 'success', 'new_status': 'Resolved'})


@admin_required
@require_POST
def dispute_dismiss_api(request, dispute_id):
    """
    Admin dismisses a dispute with a reason.
    Body: { "resolution": "..." }
    """
    try:
        body = json.loads(request.body)
    except Exception:
        body = {}

    resolution = (body.get('resolution') or '').strip()
    if len(resolution) < 5:
        return JsonResponse({'error': 'Dismissal reason is required (min 5 chars).'}, status=400)

    try:
        with connection.cursor() as cur:
            cur.execute("""
                UPDATE disputes
                SET status = 'Dismissed',
                    resolution = %s,
                    resolved_at = NOW()
                WHERE dispute_id = %s
                RETURNING dispute_id
            """, [resolution, dispute_id])
            updated = cur.fetchone()
            if not updated:
                return JsonResponse({'error': 'Dispute not found'}, status=404)

            cur.execute("""
                SELECT reported_by, provider_id, dispute_ref
                FROM disputes WHERE dispute_id = %s
            """, [dispute_id])
            rep_id, prov_id, dref = cur.fetchone()

            note_title = f"Dispute {dref or ('#' + str(dispute_id))} dismissed"
            note_body  = resolution[:140]

            for target in (rep_id, prov_id):
                if target:
                    cur.execute("""
                        INSERT INTO notification_log (user_id, title, body, type, ref_id)
                        VALUES (%s, %s, %s, 'dispute', %s)
                    """, [target, note_title, note_body, dispute_id])
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'status': 'success', 'new_status': 'Dismissed'})