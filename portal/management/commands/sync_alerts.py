from django.core.management.base import BaseCommand

from portal.services import sync_alerts


class Command(BaseCommand):
    help = "Re-evaluate overdue tasks, missed tests, missing marks and batch test-frequency alerts. Safe to run daily."

    def handle(self, *args, **opts):
        sync_alerts(force=True)
        self.stdout.write(self.style.SUCCESS("Alerts synchronised."))
