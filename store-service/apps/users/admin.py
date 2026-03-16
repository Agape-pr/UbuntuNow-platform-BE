from django.contrib import admin

from .models import Store

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'user_id', 'created_at')
