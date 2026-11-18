# web/views/strikes.py
#
# Provider strike system (admin side).
#
# POLICY (single source of truth — change the constants below, nothing else):
#
#   Active strike points   Consequence applied to the provider
#   --------------------   -----------------------------------------------
#   1                      WARNING     notification only, no restriction
#   2                      SUSPENSION  3 / 7 / 14 / 30 days (admin picks):
#                                      - forced offline, cannot go online
#                                      - cannot accept new jobs (DB trigger)
#                                      - their routes are hidden from matching
#                                      - deliveries already in progress must
#                                        still be completed (never auto-cancelled)
#                                      - suspension lifts automatically
#   3 (or a severe one)    REMOVAL     users.is_active = false (the app force-logs
#                                      them out), routes hidden. Wallet balance
#                                      stays withdrawable.
#
#   A "severe violation" strike weighs 3 points and jumps straight to removal.
#   Revoking a strike (appeal / mistake) relaxes the account:
#     3 -> 2 : reinstated, but under a fresh suspension
#     any -> <2 : suspension cleared, routes restored
#
import json
import re
from datetime import timedelta

from django.db import connection, transaction
from django.http import JsonResponse
from django.utils import timezone

from .login import admin_required
from .utils import log_admin_action

# ----------------------------------------------------------------------
# Policy constants
# ----------------------------------------------------------------------
REMOVAL_POINTS = 3
SEVERE_WEIGHT = 3
SUSPENSION_DAY_OPTIONS = (3, 7, 14, 30)
DEFAULT_SUSPENSION_DAYS = 7

REASON_CATEGORIES = [
    'Lost or damaged cargo',
    'Late or no-show',
    'Repeated cancellations',
    'Unprofessional conduct',
    'Fraud or falsified proof of delivery',
    'Safety violation',
    'Other',
]

PROTECTED_EMAIL = 'admin@packnship.com'


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
def consequence_for(points):
    if points >= REMOVAL_POINTS:
        return 'removal'
    if points == 2:
        return 'suspension'
    if points == 1:
        return 'warning'
    return 'none'


def _issuer_id(request):
    """Best-effort admin user_id (issued_by is nullable, so this never blocks)."""
    try:
        from .support import _admin_user_id
        value = _admin_user_id(request)
        return value if isinstance(value, int) else None
    except Exception:
        return None


def _parse_id(value):
    match = re.search(r'\d+', str(value or ''))
    return int(match.group()) if match else None


def _fmt_date(dt):
    return dt.strftime('%b %d, %Y') if dt else '—'


def _points(cur, provider_id):
    cur.execute("""
        SELECT COALESCE(SUM(weight), 0)
        FROM provider_strikes
        WHERE provider_id = %s AND status = 'active'
    """, [provider_id])
    return int(cur.fetchone()[0] or 0)


def _ensure_standing(cur, provider_id):
    cur.execute("""
        INSERT INTO provider_standing (provider_id)
        VALUES (%s)
        ON CONFLICT (provider_id) DO NOTHING
    """, [provider_id])


def _restrict_routes(cur, provider_id):
    cur.execute("""
        UPDATE provider_routes
           SET is_active = false, suspended_by_strike = true
         WHERE provider_id = %s AND is_active = true AND is_deleted = false
    """, [provider_id])


def _restore_routes(cur, provider_id):
    cur.execute("""
        UPDATE provider_routes
           SET is_active = NOT is_deleted, suspended_by_strike = false
         WHERE provider_id = %s AND suspended_by_strike = true
    """, [provider_id])


def _active_deliveries(cur, provider_id):
    """Deliveries still in flight — the admin must make sure these get finished."""
    cur.execute("""
        SELECT COUNT(*)
        FROM deliveries d
        LEFT JOIN LATERAL (
            SELECT status FROM delivery_status_history
            WHERE delivery_id = d.delivery_id
            ORDER BY updated_at DESC LIMIT 1
        ) dsh ON true
        WHERE d.provider_id = %s
          AND d.completed_at IS NULL
          AND d.failed_at IS NULL
          AND d.returned_at IS NULL
          AND LOWER(COALESCE(dsh.status, '')) NOT IN ('cancelled', 'completed')
    """, [provider_id])
    return int(cur.fetchone()[0] or 0)


def _notify(cur, provider_id, title, body, strike_id):
    cur.execute("""
        INSERT INTO notification_log (user_id, title, body, type, ref_id)
        VALUES (%s, %s, %s, 'account_strike', %s)
    """, [provider_id, title, body, strike_id])


# ----------------------------------------------------------------------
# Consequence engine
# ----------------------------------------------------------------------
def _apply_on_issue(cur, provider_id, points, days):
    """Tighten the account after a strike was added. Returns suspended_until or None."""
    consequence = consequence_for(points)
    _ensure_standing(cur, provider_id)

    if consequence == 'removal':
        cur.execute("UPDATE users SET is_active = false, is_online = false WHERE user_id = %s",
                    [provider_id])
        cur.execute("""
            UPDATE provider_standing
               SET removed_by_strikes = true,
                   suspended_until = NULL,
                   suspension_reason = 'Removed after reaching the strike limit',
                   updated_at = now()
             WHERE provider_id = %s
        """, [provider_id])
        _restrict_routes(cur, provider_id)
        return None

    if consequence == 'suspension':
        until = timezone.now() + timedelta(days=days)
        cur.execute("UPDATE users SET is_online = false WHERE user_id = %s", [provider_id])
        cur.execute("""
            UPDATE provider_standing
               SET suspended_until = %s,
                   suspension_reason = 'Suspended after strike 2',
                   updated_at = now()
             WHERE provider_id = %s
        """, [until, provider_id])
        _restrict_routes(cur, provider_id)
        return until

    return None  # warning: no restriction


def _apply_on_revoke(cur, provider_id, points):
    """Relax the account after a strike was revoked (never escalates)."""
    _ensure_standing(cur, provider_id)
    cur.execute("""
        SELECT removed_by_strikes, suspended_until
        FROM provider_standing
        WHERE provider_id = %s FOR UPDATE
    """, [provider_id])
    removed, until = cur.fetchone()
    now = timezone.now()

    if removed and points < REMOVAL_POINTS:
        # Reinstate (only accounts the strike policy removed — never manual deactivations).
        cur.execute("UPDATE users SET is_active = true WHERE user_id = %s", [provider_id])
        if points == 2:
            cur.execute("""
                UPDATE provider_standing
                   SET removed_by_strikes = false,
                       suspended_until = %s,
                       suspension_reason = 'Reinstated under suspension',
                       updated_at = now()
                 WHERE provider_id = %s
            """, [now + timedelta(days=DEFAULT_SUSPENSION_DAYS), provider_id])
            # routes stay hidden until lift_expired_suspensions() restores them
        else:
            cur.execute("""
                UPDATE provider_standing
                   SET removed_by_strikes = false,
                       suspended_until = NULL,
                       suspension_reason = NULL,
                       updated_at = now()
                 WHERE provider_id = %s
            """, [provider_id])
            _restore_routes(cur, provider_id)

    elif until and until > now and points < 2:
        cur.execute("""
            UPDATE provider_standing
               SET suspended_until = NULL, suspension_reason = NULL, updated_at = now()
             WHERE provider_id = %s
        """, [provider_id])
        _restore_routes(cur, provider_id)


def lift_expired():
    """Restore providers whose suspension has run out (safe to call any time)."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT public.lift_expired_suspensions()")
    except Exception as e:
        print(f"[strikes] lift_expired_suspensions failed: {e}")


# ----------------------------------------------------------------------
# Data for the "Strikes" tab on the Users page
# ----------------------------------------------------------------------
def load_strike_overview(cursor):
    lift_expired()

    cursor.execute("""
        SELECT
            u.user_id, u.first_name, u.last_name, u.email, u.is_active,
            COALESCE(sp.points, 0),
            sp.last_at,
            st.suspended_until,
            COALESCE(st.removed_by_strikes, false),
            COALESCE(rep.open_reports, 0)
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.user_id
        JOIN roles r       ON r.role_id = ur.role_id AND LOWER(r.role_name) = 'provider'
        LEFT JOIN (
            SELECT provider_id, SUM(weight) AS points, MAX(issued_at) AS last_at
            FROM provider_strikes
            WHERE status = 'active'
            GROUP BY provider_id
        ) sp ON sp.provider_id = u.user_id
        LEFT JOIN provider_standing st ON st.provider_id = u.user_id
        LEFT JOIN (
            SELECT counterparty_id, COUNT(*) AS open_reports
            FROM support_tickets
            WHERE reporter_role = 'sender'
              AND status NOT IN ('Resolved', 'Closed')
            GROUP BY counterparty_id
        ) rep ON rep.counterparty_id = u.user_id
        WHERE u.email != %s
        ORDER BY COALESCE(sp.points, 0) DESC,
                 COALESCE(rep.open_reports, 0) DESC,
                 u.created_at DESC
    """, [PROTECTED_EMAIL])

    now = timezone.now()
    rows = []
    summary = {'good': 0, 'warning': 0, 'suspended': 0, 'removed': 0, 'open_reports': 0}

    for (user_id, first, last, email, is_active, points, last_at,
         suspended_until, removed, open_reports) in cursor.fetchall():
        points = int(points or 0)
        name = " ".join(filter(None, [first, last])) or f"User #{user_id}"
        is_suspended = bool(suspended_until and suspended_until > now)

        if removed:
            key, label = 'removed', 'Removed'
        elif is_suspended:
            key, label = 'suspended', 'Suspended'
        elif not is_active:
            key, label = 'inactive', 'Deactivated'
        elif points >= 2:
            key, label = 'final', 'Final warning'
        elif points == 1:
            key, label = 'warning', 'Warning'
        else:
            key, label = 'good', 'Good standing'

        if key == 'removed':
            summary['removed'] += 1
        elif key == 'suspended':
            summary['suspended'] += 1
        elif key in ('warning', 'final'):
            summary['warning'] += 1
        elif key == 'good':
            summary['good'] += 1
        summary['open_reports'] += int(open_reports or 0)

        rows.append({
            'raw_id': user_id,
            'id': f"USI{user_id}",
            'name': name,
            'initial': name[:1].upper(),
            'email': email or '—',
            'points': min(points, REMOVAL_POINTS),
            'standing': key,
            'standing_label': label,
            'suspended_until': _fmt_date(suspended_until) if is_suspended else '',
            'open_reports': int(open_reports or 0),
            'last_strike': _fmt_date(last_at),
            'search': f"{name} {email} {label} USI{user_id}".lower(),
        })

    return rows, summary


# ----------------------------------------------------------------------
# JSON APIs (CSRF protected — the page sends X-CSRFToken)
# ----------------------------------------------------------------------
@admin_required
def provider_strikes_api(request, user_id):
    """GET: strike history + standing + open reports for one provider."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    lift_expired()

    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.strike_id, s.reason_category, s.reason, s.weight, s.consequence,
                   s.suspension_days, s.status, s.issued_at, s.revoked_at, s.revoke_reason,
                   t.ticket_ref,
                   COALESCE(a.first_name || ' ' || a.last_name, 'Admin')
            FROM provider_strikes s
            LEFT JOIN support_tickets t ON t.ticket_id = s.ticket_id
            LEFT JOIN users a           ON a.user_id = s.issued_by
            WHERE s.provider_id = %s
            ORDER BY s.issued_at DESC, s.strike_id DESC
        """, [user_id])
        strikes = [{
            'strike_id': r[0], 'reason_category': r[1], 'reason': r[2], 'weight': r[3],
            'consequence': r[4], 'suspension_days': r[5], 'status': r[6],
            'issued_at': _fmt_date(r[7]), 'revoked_at': _fmt_date(r[8]),
            'revoke_reason': r[9] or '', 'ticket_ref': r[10] or '', 'issued_by': r[11],
        } for r in cur.fetchall()]

        points = _points(cur, user_id)

        cur.execute("""
            SELECT removed_by_strikes, suspended_until
            FROM provider_standing WHERE provider_id = %s
        """, [user_id])
        st = cur.fetchone()
        removed = bool(st[0]) if st else False
        until = st[1] if st else None
        suspended = bool(until and until > timezone.now())

        # Every report a sender filed against this provider (newest first). Resolved
        # reports matter most: they are the usual basis for a strike.
        cur.execute("""
            SELECT t.ticket_id, t.ticket_ref, t.sub_issue, t.status, t.created_at, t.resolution,
                   EXISTS (
                       SELECT 1 FROM provider_strikes s
                       WHERE s.ticket_id = t.ticket_id AND s.status = 'active'
                   ) AS has_strike
            FROM support_tickets t
            WHERE t.counterparty_id = %s
              AND t.reporter_role = 'sender'
            ORDER BY t.created_at DESC
            LIMIT 15
        """, [user_id])
        reports = [{
            'ticket_id': r[0], 'ticket_ref': r[1] or f"#{r[0]}",
            'sub_issue': r[2], 'status': r[3], 'created_at': _fmt_date(r[4]),
            'resolution': r[5] or '', 'has_strike': bool(r[6]),
            'open': r[3] not in ('Resolved', 'Closed'),
        } for r in cur.fetchall()]

        active_deliveries = _active_deliveries(cur, user_id)

    return JsonResponse({
        'points': min(points, REMOVAL_POINTS),
        'removed': removed,
        'suspended': suspended,
        'suspended_until': _fmt_date(until) if suspended else '',
        'next_consequence': consequence_for(points + 1),
        'strikes': strikes,
        'reports': reports,
        'active_deliveries': active_deliveries,
        'categories': REASON_CATEGORIES,
        'suspension_options': list(SUSPENSION_DAY_OPTIONS),
        'default_days': DEFAULT_SUSPENSION_DAYS,
    })


class StrikeError(Exception):
    """A user-facing validation error raised inside a strike/decision transaction."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _resolve_ticket(cur, ticket_ref, provider_id):
    """Look a ticket up by ref/id and make sure it involves this provider."""
    cur.execute("""
        SELECT ticket_id, delivery_id, reporter_id, counterparty_id
        FROM support_tickets
        WHERE ticket_ref = %s OR ticket_id::text = %s
        LIMIT 1
    """, [ticket_ref, ticket_ref.lstrip('#')])
    t = cur.fetchone()
    if not t:
        raise StrikeError(f'Ticket "{ticket_ref}" was not found.', 404)
    if provider_id not in (t[2], t[3]):
        raise StrikeError('That ticket does not involve this provider.', 400)
    return t[0], t[1]


def _issue_strike_tx(cur, admin_id, provider_id, category, reason, severe, days,
                     ticket_id=None, delivery_id=None):
    """
    Issue a strike and apply its consequence. MUST run inside an open
    transaction.atomic() with a cursor. Raises StrikeError on validation problems.
    """
    reason = (reason or '').strip()
    if category not in REASON_CATEGORIES:
        raise StrikeError('Choose a reason category.')
    if len(reason) < 10:
        raise StrikeError('Describe the reason (at least 10 characters). The provider will see it.')
    if days not in SUSPENSION_DAY_OPTIONS:
        days = DEFAULT_SUSPENSION_DAYS

    # Lock the provider row so two admins can't race each other.
    cur.execute("""
        SELECT u.first_name, u.last_name
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.user_id
        JOIN roles r       ON r.role_id = ur.role_id
        WHERE u.user_id = %s AND LOWER(r.role_name) = 'provider'
        FOR UPDATE OF u
    """, [provider_id])
    provider = cur.fetchone()
    if not provider:
        raise StrikeError('Provider not found.', 404)

    current = _points(cur, provider_id)
    if current >= REMOVAL_POINTS:
        raise StrikeError('This provider is already at the strike limit. '
                          'Revoke a strike first if the removal should be reviewed.', 409)

    if ticket_id:
        cur.execute("""
            SELECT 1 FROM provider_strikes
            WHERE provider_id = %s AND ticket_id = %s AND status = 'active'
        """, [provider_id, ticket_id])
        if cur.fetchone():
            raise StrikeError('A strike was already issued for that ticket.', 409)

    weight = SEVERE_WEIGHT if severe else 1
    new_points = current + weight
    consequence = consequence_for(new_points)

    cur.execute("""
        INSERT INTO provider_strikes
            (provider_id, reason_category, reason, weight, consequence,
             suspension_days, ticket_id, delivery_id, issued_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING strike_id
    """, [provider_id, category, reason, weight, consequence,
          days if consequence == 'suspension' else None,
          ticket_id, delivery_id, admin_id])
    strike_id = cur.fetchone()[0]

    until = _apply_on_issue(cur, provider_id, new_points, days)
    shown = min(new_points, REMOVAL_POINTS)

    if consequence == 'removal':
        _notify(cur, provider_id, 'Account removed',
                f"Strike {shown}/{REMOVAL_POINTS} — {category}. Your account has been removed "
                f"from Pack-N-Ship. Contact support if you believe this is a mistake.",
                strike_id)
    elif consequence == 'suspension':
        _notify(cur, provider_id, 'Account suspended',
                f"Strike {shown}/{REMOVAL_POINTS} — {category}. Your account is suspended "
                f"until {_fmt_date(until)}. You can't go online or accept new jobs until then. "
                f"One more strike removes your account.",
                strike_id)
    else:
        _notify(cur, provider_id, 'Account warning',
                f"Strike {shown}/{REMOVAL_POINTS} — {category}. This is a warning. "
                f"Another strike will suspend your account. Open Account Health for details.",
                strike_id)

    return {
        'strike_id': strike_id,
        'consequence': consequence,
        'points': shown,
        'suspended_until': _fmt_date(until) if until else '',
        'active_deliveries': _active_deliveries(cur, provider_id) if consequence != 'warning' else 0,
        'name': " ".join(filter(None, provider)),
        'severe': severe,
    }


def _log_strike(request, provider_id, r, category):
    log_admin_action(
        request,
        f"Issued strike {r['points']}/{REMOVAL_POINTS} "
        f"({r['consequence']}{' – severe' if r['severe'] else ''}) to provider "
        f"USI{provider_id} {r['name']}: {category}"
    )


@admin_required
def issue_strike_api(request):
    """POST: issue a strike and apply the consequence for the new total."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    provider_id = _parse_id(data.get('provider_id'))
    category = (data.get('reason_category') or '').strip()
    ticket_ref = str(data.get('ticket_ref') or '').strip()
    try:
        days = int(data.get('suspension_days') or DEFAULT_SUSPENSION_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_SUSPENSION_DAYS
    if not provider_id:
        return JsonResponse({'error': 'Invalid provider.'}, status=400)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                ticket_id = delivery_id = None
                if ticket_ref:
                    ticket_id, delivery_id = _resolve_ticket(cur, ticket_ref, provider_id)
                result = _issue_strike_tx(
                    cur, _issuer_id(request), provider_id, category,
                    data.get('reason'), bool(data.get('severe')), days, ticket_id, delivery_id,
                )
        _log_strike(request, provider_id, result, category)
        return JsonResponse({'success': True, **{k: result[k] for k in (
            'strike_id', 'consequence', 'points', 'suspended_until', 'active_deliveries')}})
    except StrikeError as e:
        return JsonResponse({'error': e.message}, status=e.status)
    except Exception as e:
        print(f"[issue_strike_api] error: {e}")
        return JsonResponse({'error': 'Could not issue the strike.'}, status=500)


# ----------------------------------------------------------------------
# Ticket review + decision (the admin reads a report and rules on it)
# ----------------------------------------------------------------------
@admin_required
def ticket_review_api(request, ticket_id):
    """GET: everything an admin needs to review one report."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    with connection.cursor() as cur:
        cur.execute("""
            SELECT t.ticket_id, t.ticket_ref, t.type, t.category, t.sub_issue, t.description,
                   t.requested_resolution, t.status, t.resolution, t.created_at, t.resolved_at,
                   t.reporter_id, t.reporter_role, t.counterparty_id, t.delivery_id, t.request_id,
                   COALESCE(rp.first_name || ' ' || rp.last_name, 'Unknown'),
                   COALESCE(cp.first_name || ' ' || cp.last_name, '—'),
                   EXISTS (SELECT 1 FROM provider_strikes s
                           WHERE s.ticket_id = t.ticket_id AND s.status = 'active')
            FROM support_tickets t
            LEFT JOIN users rp ON rp.user_id = t.reporter_id
            LEFT JOIN users cp ON cp.user_id = t.counterparty_id
            WHERE t.ticket_id = %s
        """, [ticket_id])
        r = cur.fetchone()
        if not r:
            return JsonResponse({'error': 'Ticket not found.'}, status=404)

        cur.execute("""
            SELECT m.sender_kind,
                   COALESCE(u.first_name || ' ' || u.last_name, ''),
                   m.body, jsonb_array_length(m.attachments), m.is_internal, m.created_at
            FROM ticket_messages m
            LEFT JOIN users u ON u.user_id = m.sender_id
            WHERE m.ticket_id = %s
            ORDER BY m.created_at, m.message_id
        """, [ticket_id])
        messages = [{
            'kind': m[0], 'name': m[1], 'body': m[2], 'photos': int(m[3] or 0),
            'internal': bool(m[4]), 'at': m[5].strftime('%b %d, %Y %H:%M') if m[5] else '—',
        } for m in cur.fetchall()]

    provider_id = r[13] if r[12] == 'sender' else None
    return JsonResponse({
        'ticket_id': r[0], 'ticket_ref': r[1] or f"#{r[0]}", 'type': r[2], 'category': r[3],
        'sub_issue': r[4], 'description': r[5], 'requested_resolution': r[6] or '',
        'status': r[7], 'resolution': r[8] or '', 'created_at': _fmt_date(r[9]),
        'resolved_at': _fmt_date(r[10]), 'closed': r[7] in ('Resolved', 'Closed'),
        'reporter_name': r[16], 'reporter_role': r[12], 'counterparty_name': r[17],
        'delivery_id': r[14], 'request_id': r[15],
        'provider_id': provider_id, 'has_strike': bool(r[18]),
        'messages': messages,
        'categories': REASON_CATEGORIES,
        'suspension_options': list(SUSPENSION_DAY_OPTIONS),
        'default_days': DEFAULT_SUSPENSION_DAYS,
    })


def _ticket_event(cur, ticket_id, status, note, actor_id):
    cur.execute("""
        INSERT INTO ticket_events (ticket_id, status, note, actor_id)
        VALUES (%s, %s, %s, %s)
    """, [ticket_id, status, note, actor_id])


@admin_required
def ticket_decide_api(request, ticket_id):
    """
    POST: record the admin's decision on a report.

    action = uphold      Resolve in the reporter's favour. Optionally issue a strike to the
                         reported provider in the SAME transaction (strike.issue = true).
             dismiss     Resolve without action against the provider.
             in_review   Mark the ticket 'In Review'.
             ask_reporter  Send the reporter a message and set 'Awaiting Reporter'.

    This records the decision only. Refunds / escrow release stay on the Escrow Disputes page.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    text = (data.get('text') or '').strip()
    strike = data.get('strike') or {}
    admin_id = _issuer_id(request)

    if action not in ('uphold', 'dismiss', 'in_review', 'ask_reporter'):
        return JsonResponse({'error': 'Choose an action.'}, status=400)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT status, reporter_id, counterparty_id, reporter_role,
                           delivery_id, legacy_dispute_id, ticket_ref
                    FROM support_tickets WHERE ticket_id = %s FOR UPDATE
                """, [ticket_id])
                row = cur.fetchone()
                if not row:
                    raise StrikeError('Ticket not found.', 404)
                status, reporter_id, counterparty_id, reporter_role, delivery_id, legacy_id, ref = row
                ref = ref or f"#{ticket_id}"
                if status in ('Resolved', 'Closed'):
                    raise StrikeError('This ticket already has a decision.', 409)

                strike_result = None

                if action in ('uphold', 'dismiss'):
                    if len(text) < 10:
                        raise StrikeError('Write the decision (at least 10 characters). Both sides will see it.')

                    if action == 'uphold' and strike.get('issue'):
                        if reporter_role != 'sender' or not counterparty_id:
                            raise StrikeError('Strikes can only be issued on sender reports against a provider.')
                        try:
                            days = int(strike.get('suspension_days') or DEFAULT_SUSPENSION_DAYS)
                        except (TypeError, ValueError):
                            days = DEFAULT_SUSPENSION_DAYS
                        strike_result = _issue_strike_tx(
                            cur, admin_id, counterparty_id,
                            (strike.get('reason_category') or '').strip(),
                            text,  # the decision text doubles as the strike reason the provider sees
                            bool(strike.get('severe')), days, ticket_id, delivery_id,
                        )

                    cur.execute("""
                        UPDATE support_tickets
                           SET status = 'Resolved', resolution = %s, resolved_at = now(),
                               last_activity_at = now(), updated_at = now(),
                               assigned_admin_id = COALESCE(assigned_admin_id, %s)
                         WHERE ticket_id = %s
                    """, [text, admin_id, ticket_id])
                    _ticket_event(cur, ticket_id, 'Resolved',
                                  ('Report upheld' if action == 'uphold' else 'Report dismissed'), admin_id)

                    if legacy_id:  # keep the legacy disputes row in step
                        cur.execute("""
                            UPDATE disputes
                               SET status = %s, resolution = %s, resolved_at = now(),
                                   resolved_by = %s, updated_at = now()
                             WHERE dispute_id = %s
                        """, ['Resolved' if action == 'uphold' else 'Dismissed', text, admin_id, legacy_id])

                    verdict = 'upheld' if action == 'uphold' else 'not upheld'
                    cur.execute("""
                        INSERT INTO notification_log (user_id, title, body, type, ref_id)
                        VALUES (%s, %s, %s, 'ticket_update', %s)
                    """, [reporter_id, 'Your report has a decision',
                          f"Report {ref} was reviewed and {verdict}. Open the ticket to read the decision.",
                          ticket_id])
                    if counterparty_id:
                        cur.execute("""
                            INSERT INTO notification_log (user_id, title, body, type, ref_id)
                            VALUES (%s, %s, %s, 'ticket_update', %s)
                        """, [counterparty_id, 'A report about you was decided',
                              f"Report {ref} was reviewed and {verdict}. Open the ticket to read the decision.",
                              ticket_id])

                elif action == 'in_review':
                    cur.execute("""
                        UPDATE support_tickets
                           SET status = 'In Review', last_activity_at = now(), updated_at = now(),
                               assigned_admin_id = COALESCE(assigned_admin_id, %s)
                         WHERE ticket_id = %s
                    """, [admin_id, ticket_id])
                    _ticket_event(cur, ticket_id, 'In Review', 'Staff started reviewing', admin_id)

                else:  # ask_reporter
                    if len(text) < 5:
                        raise StrikeError('Write what you need from the reporter.')
                    cur.execute("""
                        INSERT INTO ticket_messages (ticket_id, sender_id, sender_kind, body, audience_id)
                        VALUES (%s, %s, 'staff', %s, %s)
                    """, [ticket_id, admin_id, text, reporter_id])
                    cur.execute("""
                        UPDATE support_tickets
                           SET status = 'Awaiting Reporter', last_activity_at = now(), updated_at = now(),
                               assigned_admin_id = COALESCE(assigned_admin_id, %s)
                         WHERE ticket_id = %s
                    """, [admin_id, ticket_id])
                    _ticket_event(cur, ticket_id, 'Awaiting Reporter', 'Staff asked for more details', admin_id)
                    cur.execute("""
                        INSERT INTO notification_log (user_id, title, body, type, ref_id)
                        VALUES (%s, %s, %s, 'ticket_update', %s)
                    """, [reporter_id, 'We need more details',
                          f"Support replied on report {ref}. Open the ticket to answer.", ticket_id])

        label = {'uphold': 'Upheld', 'dismiss': 'Dismissed',
                 'in_review': 'Marked in review', 'ask_reporter': 'Asked reporter for details'}[action]
        log_admin_action(request, f"Ticket {ref}: {label}")
        if strike_result:
            _log_strike(request, counterparty_id, strike_result, (strike.get('reason_category') or '').strip())

        out = {'success': True, 'action': action}
        if strike_result:
            out.update({k: strike_result[k] for k in (
                'consequence', 'points', 'suspended_until', 'active_deliveries')})
        return JsonResponse(out)

    except StrikeError as e:
        return JsonResponse({'error': e.message}, status=e.status)
    except Exception as e:
        print(f"[ticket_decide_api] error: {e}")
        return JsonResponse({'error': 'Could not save the decision.'}, status=500)


@admin_required
def revoke_strike_api(request, strike_id):
    """POST: revoke a strike (appeal upheld / issued by mistake) and relax the account."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    revoke_reason = (data.get('revoke_reason') or '').strip()
    if len(revoke_reason) < 5:
        return JsonResponse({'error': 'Give a short reason for revoking this strike.'}, status=400)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT provider_id, status, reason_category
                    FROM provider_strikes
                    WHERE strike_id = %s FOR UPDATE
                """, [strike_id])
                row = cur.fetchone()
                if not row:
                    return JsonResponse({'error': 'Strike not found.'}, status=404)
                provider_id, status, category = row
                if status != 'active':
                    return JsonResponse({'error': 'This strike is already revoked.'}, status=409)

                cur.execute("SELECT user_id FROM users WHERE user_id = %s FOR UPDATE", [provider_id])

                cur.execute("""
                    UPDATE provider_strikes
                       SET status = 'revoked', revoked_by = %s, revoked_at = now(), revoke_reason = %s
                     WHERE strike_id = %s
                """, [_issuer_id(request), revoke_reason, strike_id])

                points = _points(cur, provider_id)
                _apply_on_revoke(cur, provider_id, points)

                _notify(cur, provider_id, 'A strike was removed',
                        f"The strike for “{category}” was reviewed and removed. "
                        f"You now have {min(points, REMOVAL_POINTS)}/{REMOVAL_POINTS} strikes.",
                        strike_id)

        log_admin_action(request, f"Revoked strike #{strike_id} for provider USI{provider_id}: {revoke_reason}")
        return JsonResponse({'success': True, 'points': min(points, REMOVAL_POINTS)})

    except Exception as e:
        print(f"[revoke_strike_api] error: {e}")
        return JsonResponse({'error': 'Could not revoke the strike.'}, status=500)