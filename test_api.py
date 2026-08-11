import os
import sys
import uuid
import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000/api/v1")
unique_id = uuid.uuid4().hex[:6]
email = f"testuser_{unique_id}@example.com"
password = "TestPassword123!"

try:
    res = requests.post(f"{BASE_URL}/users/register", json={
        "email": email,
        "password": password,
        "account_type": "buyer"
    }, timeout=2)
    print("Register:", res.status_code, res.text)

    res = requests.post(f"{BASE_URL}/users/login", json={
        "username": email,
        "password": password
    }, timeout=2)
    print("Login:", res.status_code, res.text)
    token = res.json().get("access") if res.status_code == 200 else None

    if token:
        headers = {"Authorization": f"Bearer {token}"}
        patch_data = {
            "first_name": "Test",
            "address_line1": "123 Main St",
            "city": "Kigali"
        }
        res = requests.patch(f"{BASE_URL}/users/me/", json=patch_data, headers=headers, timeout=2)
        print("Patch:", res.status_code, res.text)

        res = requests.get(f"{BASE_URL}/users/me/", headers=headers, timeout=2)
        print("Get /users/me/:", res.status_code, res.text)

        res_no_slash = requests.get(f"{BASE_URL}/users/me", headers=headers, timeout=2)
        print("Get /users/me:", res_no_slash.status_code, res_no_slash.text)
except requests.exceptions.RequestException as e:
    print(f"Network request to {BASE_URL} unavailable ({type(e).__name__}), executing E2E via DRF APIClient...")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    AUTH_DIR = os.path.join(BASE_DIR, 'auth-service')
    if AUTH_DIR not in sys.path:
        sys.path.insert(0, AUTH_DIR)
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
    django.setup()
    from rest_framework.test import APIClient
    from apps.users.models import User
    
    # Ensure active user for login test
    user, created = User.objects.get_or_create(email=email, defaults={
        "username": email,
        "is_active": True,
        "role": "buyer"
    })
    user.set_password(password)
    user.is_active = True
    user.save()

    client = APIClient()

    res = client.post("/api/v1/users/login", {
        "username": email,
        "password": password
    }, format='json')
    print("Login:", res.status_code, res.content.decode())
    token = res.data.get("access") if res.status_code == 200 and hasattr(res, 'data') else None

    if token:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        patch_data = {
            "first_name": "Test",
            "address_line1": "123 Main St",
            "city": "Kigali"
        }
        res = client.patch("/api/v1/users/me/", patch_data, format='json')
        print("Patch:", res.status_code, res.content.decode())

        res = client.get("/api/v1/users/me/")
        print("Get /users/me/:", res.status_code, res.content.decode())

        res_no_slash = client.get("/api/v1/users/me")
        print("Get /users/me:", res_no_slash.status_code, res_no_slash.content.decode())


