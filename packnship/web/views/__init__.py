# views/__init__.py

from .login import admin_login, custom_logout
from .dashboard import dashboard
from .users import users_page
from .users import toggle_user_status
from .provider_verification import (
    provider_verification, approve_provider, reject_provider, provider_photo
)
from .vehicle_verification import (
    vehicle_verification, approve_vehicle, reject_vehicle, vehicle_document
)
from .deliveries import deliveries
from .escrow_payments import (
    escrow_payments, process_escrow_action, toggle_escrow_freeze
)

from .disputes import (
    admin_disputes_view,
    disputes_list_api,
    dispute_detail_api,
    dispute_resolve_api,
    dispute_dismiss_api,
)

from .ratings_feedback import ratings_feedback
from .reports import reports
from .settings import settings_page
from .support import (
    admin_support_view,
    support_tickets_api,
    support_thread_api,
    support_reply_api,
    support_status_api,
    chat_start_room_api,
    chat_thread_api,
    chat_send_api,
    _admin_user_id,
)