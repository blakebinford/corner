from django.core.management.base import BaseCommand
from competitions.models import Competition

class Command(BaseCommand):
    help = "Generate AI summaries for competitions without one"

    def handle(self, *args, **options):
        for comp in Competition.objects.all():
            if not comp.auto_summary and not comp.sponsor_logos.exists():
                self.stdout.write(f"Generating summary for: {comp.name}")
                comp.generate_auto_summary()
