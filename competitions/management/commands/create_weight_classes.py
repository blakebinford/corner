from django.core.management.base import BaseCommand
from accounts.models import WeightClass
from competitions.models import Federation, Division, DivisionWeightClass

class Command(BaseCommand):
    help = "Create weight classes for federations and tie them to divisions."

    def handle(self, *args, **kwargs):
        weight_classes_data = [
            {
                'federation_name': 'Strongman Corporation',
                'weight_classes': [
                    {'name': 175.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 200.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 231.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 265.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 265.5, 'gender': 'Male', 'weight_d': '+'},
                    {'name': 125.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 140.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 160.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 180.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 180.5, 'gender': 'Female', 'weight_d': '+'},
                ],
            },
            {
                'federation_name': 'United States Strongman',
                'weight_classes': [
                    {'name': 181.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 165.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 198.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 220.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 275.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 308.0, 'gender': 'Male', 'weight_d': 'u'},
                    {'name': 308.5, 'gender': 'Male', 'weight_d': '+'},
                    {'name': 123.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 132.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 148.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 165.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 181.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 198.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 242.0, 'gender': 'Female', 'weight_d': 'u'},
                    {'name': 242.0, 'gender': 'Female', 'weight_d': '+'},
                ],
            },
        ]

        divisions = ['pro', 'adaptive', 'open', 'master', 'teen', 'novice']

        # Create or get Unsanctioned federation
        unsanctioned_federation, _ = Federation.objects.get_or_create(name='Unsanctioned')

        for federation_data in weight_classes_data:
            federation, _ = Federation.objects.get_or_create(name=federation_data['federation_name'])
            for weight_class_data in federation_data['weight_classes']:
                weight_class, _ = WeightClass.objects.get_or_create(
                    name=weight_class_data['name'],
                    gender=weight_class_data['gender'],
                    federation=federation,
                    weight_d=weight_class_data['weight_d'],
                )
                self.stdout.write(self.style.SUCCESS(f"Created weight class {weight_class} for {federation.name}"))

            # Tie weight classes to divisions
            for division_name in divisions:
                division, _ = Division.objects.get_or_create(name=division_name)
                for weight_class_data in federation_data['weight_classes']:
                    weight_class = WeightClass.objects.get(
                        name=weight_class_data['name'],
                        gender=weight_class_data['gender'],
                        federation=federation,
                        weight_d=weight_class_data['weight_d'],
                    )
                    DivisionWeightClass.objects.get_or_create(
                        division=division,
                        weight_class=weight_class,
                        gender=weight_class.gender,  # Assign gender from WeightClass
                    )

        # Mirror weight classes and divisions for Unsanctioned from United States Strongman
        uss_federation = Federation.objects.get(name='United States Strongman')
        uss_weight_classes = WeightClass.objects.filter(federation=uss_federation)

        for weight_class in uss_weight_classes:
            unsanctioned_class, _ = WeightClass.objects.get_or_create(
                name=weight_class.name,
                gender=weight_class.gender,
                federation=unsanctioned_federation,
                weight_d=weight_class.weight_d,
            )
            for division_name in divisions:
                division = Division.objects.get(name=division_name)
                DivisionWeightClass.objects.get_or_create(
                    division=division,
                    weight_class=unsanctioned_class,
                    gender=unsanctioned_class.gender,  # Assign gender from Unsanctioned WeightClass
                )
        self.stdout.write(self.style.SUCCESS("Successfully created weight classes for Unsanctioned federation."))
