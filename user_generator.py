import factory
from faker import Faker
from django.contrib.auth.hashers import make_password
from accounts.models import User, AthleteProfile
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_crazy_service.settings')
django.setup()

fake = Faker()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n:
 f'{fake.user_name()}{n}')
    email = factory.LazyAttribute(lambda o: f'{o.username}@{fake.domain_name()}')
    password = make_password('testpassworD1')
    email_verified = True  # Set email_verified to True for testing
    role = 'athlete'

class AthleteProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AthleteProfile

    user = factory.SubFactory(UserFactory)
    gender = factory.LazyFunction(lambda: fake.random_element(elements=('male', 'female')))

def create_test_users(num_users=10):
    for _ in range(num_users):
        user = UserFactory()
        AthleteProfileFactory(user=user)

# Call the function to create test users
create_test_users()