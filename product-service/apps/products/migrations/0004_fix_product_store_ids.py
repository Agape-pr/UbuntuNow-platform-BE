"""
Data migration: fix_product_store_ids_from_user_ids

Problem:
  Products were mistakenly saved with store_id = user_id (the auth-service user PK)
  instead of store_id = Store.id (the store-service Store table PK) due to a bug
  in the IsSeller permission fallback that used `user_id` when `id` was intended.

Fix:
  For every unique store_id currently on a product, ask the store-service:
  "Is this store_id actually a user_id?" (i.e. does a store exist with user_id=X?)
  If yes AND the real Store.id is different → update all those products.

This runs automatically on the next `python manage.py migrate`.
It is safe to run multiple times (idempotent).
"""

from django.db import migrations
import os
import requests as http_requests


def fix_store_ids(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')

    # Get all unique store_id values currently stored
    existing_ids = list(
        Product.objects.values_list('store_id', flat=True).distinct()
    )
    print(f"[fix_store_ids] Found {len(existing_ids)} unique store_id(s) in DB: {existing_ids}")

    fixed = 0
    for candidate_id in existing_ids:
        try:
            # Ask store-service: does a store exist where user_id = candidate_id ?
            res = http_requests.get(
                f"{store_url}/api/v1/users/internal/stores/{candidate_id}/",
                timeout=5,
            )
        except Exception as e:
            print(f"[fix_store_ids] store_id={candidate_id}: store-service unreachable — {e}")
            continue

        if res.status_code != 200:
            print(f"[fix_store_ids] store_id={candidate_id}: no store found with user_id={candidate_id} — skipping")
            continue

        store_data = res.json()
        real_store_id = store_data.get('id')       # Store table PK
        store_name    = store_data.get('store_name', '?')

        if real_store_id is None:
            print(f"[fix_store_ids] store_id={candidate_id}: response had no 'id' — skipping")
            continue

        if real_store_id == candidate_id:
            print(f"[fix_store_ids] store_id={candidate_id} ({store_name}): already correct ✓")
            continue

        # candidate_id was a user_id; real Store.id is different — fix it
        affected_qs = Product.objects.filter(store_id=candidate_id)
        count = affected_qs.count()
        affected_qs.update(store_id=real_store_id)
        print(
            f"[fix_store_ids] ✅ {store_name}: updated {count} product(s) "
            f"store_id {candidate_id} (user_id) → {real_store_id} (Store.pk)"
        )
        fixed += count

    print(f"[fix_store_ids] Done. Fixed {fixed} product(s) total.")


def reverse_fix(apps, schema_editor):
    # Intentionally a no-op — we can't safely reverse without original data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_change_category_to_string'),
    ]

    operations = [
        migrations.RunPython(fix_store_ids, reverse_code=reverse_fix),
    ]
