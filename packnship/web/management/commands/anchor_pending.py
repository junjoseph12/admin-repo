# web/management/commands/anchor_pending.py
# Fully hands-off anchoring. Schedule it (cron / Render cron job / Railway scheduler), e.g. every 5 minutes:
#     python manage.py anchor_pending
# NOTE: web/management/ and web/management/commands/ each need an (empty) __init__.py.
from django.core.management.base import BaseCommand

from web.views.blockchain_ledger import anchor_pending_records


class Command(BaseCommand):
    help = "Anchor every un-anchored record (KYC, escrow, deliveries, QR, reviews, transactions, withdrawals) on the blockchain."

    def add_arguments(self, parser):
        parser.add_argument('--max-seconds', type=int, default=120, help='Stop after this many seconds (default 120).')

    def handle(self, *args, **options):
        result = anchor_pending_records(max_seconds=options['max_seconds'])
        if result['busy']:
            self.stdout.write('Another anchoring run is already in progress - skipped.')
            return
        self.stdout.write(self.style.SUCCESS(
            f"Anchored {result['anchored']}, failed {result['failed']}, "
            f"backing off {result['skipped']}, left for next run {result['remaining']}."
        ))
        for err in result['errors']:
            self.stdout.write(self.style.WARNING(f"  {err}"))