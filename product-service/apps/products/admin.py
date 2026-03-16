from django.contrib import admin
from .models import Product, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'store_id', 'price', 'stock_quantity', 'is_active')
    list_filter = ('store_id', 'category', 'is_active')
    search_fields = ('name', 'description')
