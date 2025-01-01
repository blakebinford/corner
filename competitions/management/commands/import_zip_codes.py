import csv
import sys

from django.core.management.base import BaseCommand

from competitions.models import ZipCode  # Adjust the import path as needed

class Command(BaseCommand):
    help = 'Import zip code data from a text file'

    def handle(self, *args, **options):
        with open('/home/blake/PycharmProjects/ComPodium/competitions/management/commands/US.txt', 'r') as file:
            reader = csv.reader(file, delimiter='\t')  # Assuming tab-separated values
            next(reader)  # Skip the header row if present
            for row in reader:
                zip_code = row[1]  # Assuming zip code is in the first column
                latitude = float(row[9])  # Assuming latitude is in the second column
                longitude = float(row[10])  # Assuming longitude is in the third column
                ZipCode.objects.create(zip_code=zip_code, latitude=latitude, longitude=longitude)

        self.stdout.write(self.style.SUCCESS('Zip code data imported successfully'))