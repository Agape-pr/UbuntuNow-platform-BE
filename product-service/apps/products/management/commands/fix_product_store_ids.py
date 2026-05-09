"""
Management command: fix_product_store_ids

Problem:
  Products were mistakenly saved with store_id = user_id (the auth-service user PK)
  instead of store_id = Store.id (the store-service Store table PK).
  These are different numbers, so store pages showed 0 products.

Fix:
  1. Fetch all stores from the store-service (each has both .id and .user_id)
  2. For every store where id != user_id, find products where store_id == user_id
  3. Update those products' store_id to the correct Store.id value

Usage:
  python manage.py fix_product_store_ids           # dry run (safe, shows what would change)
  python manage.py fix_product_store_ids --apply   # actually update the DB
"""

import os
import requests
from django.core.management.base import BaseCommand
from apps.products.models import Product


class Command(BaseCommand):
    help = "Fix products whose store_id was incorrectly set to user_id instead of Store.id"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Apply the fix. Without this flag the command is a dry-run.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')

        self.stdout.write(self.style.WARNING(
            f"{'[DRY RUN] ' if not apply else '[APPLYING] '}"
            f"Connecting to store-service at {store_url} …"
        ))

        # ── 1. Fetch all stores ──────────────────────────────────────────
        # The internal list endpoint returns all stores with both id and user_id
        try:
            # Fetch store list — try a range of user_ids (brute-force safe approach)
            # We'll query the public store endpoint doesn't list all stores,
            # so we use the internal retrieve endpoint by scanning known products
            
            # Get all unique store_ids currently in the product DB
            existing_store_ids = list(
                Product.objects.values_list('store_id', flat=True).distinct()
            )
            self.stdout.write(f"Found {len(existing_store_ids)} unique store_id values in products DB: {existing_store_ids}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to read products: {e}"))
            return

        total_fixed = 0

        for wrong_store_id in existing_store_ids:
            # ── 2. Ask store-service: is this store_id actually a user_id? ──
            try:
                res = requests.get(
                    f"{store_url}/api/v1/users/internal/stores/{wrong_store_id}/",
                    timeout=5,
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f"  store_id={wrong_store_id}: could not reach store-service — {e}"
                ))
                continue

            if res.status_code != 200:
                self.stdout.write(
                    f"  store_id={wrong_store_id}: store-service returned {res.status_code} "
                    f"(not a user_id, or store doesn't exist — skip)"
                )
                continue

            store_data = res.json()
            real_store_id = store_data.get('id')
            user_id       = store_data.get('user_id')
            store_name    = store_data.get('store_name', '?')

            if real_store_id is None:
                self.stdout.write(self.style.WARNING(
                    f"  store_id={wrong_store_id}: store-service response had no 'id' field — skip"
                ))
                continue

            if real_store_id == wrong_store_id:
                # Already correct — this store_id IS the Store.id
                self.stdout.write(
                    f"  store_id={wrong_store_id} ({store_name}): already correct ✓"
                )
                continue

            # ── 3. This was saved as user_id but real Store.id is different ──
            affected = Product.objects.filter(store_id=wrong_store_id)
            count = affected.count()

            self.stdout.write(self.style.WARNING(
                f"  store_id={wrong_store_id} ({store_name}): WRONG "
                f"(user_id={user_id}, correct Store.id={real_store_id}) "
                f"— {count} product(s) affected"
            ))

            if apply and count > 0:
                affected.update(store_id=real_store_id)
                self.stdout.write(self.style.SUCCESS(
                    f"    ✅ Updated {count} product(s): store_id {wrong_store_id} → {real_store_id}"
                ))
                total_fixed += count
            elif count > 0:
                self.stdout.write(
                    f"    [DRY RUN] Would update {count} product(s): store_id {wrong_store_id} → {real_store_id}"
                )

        # ── Summary ──────────────────────────────────────────────────────
        if apply:
            self.stdout.write(self.style.SUCCESS(
                f"\nDone. Fixed {total_fixed} product(s) total."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"\nDry run complete. Run with --apply to make the changes."
            ))
