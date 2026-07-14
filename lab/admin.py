from django.contrib import admin
from django.contrib.auth.models import Group, User

from .models import Inventory, TransactionHistory

admin.site.site_header = "시약 관리 시스템"
admin.site.site_title = "시약 관리 시스템"
admin.site.index_title = "관리자 페이지"


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("id", "part", "item_code", "item_name", "lot_no", "reagent_type", "current_stock", "disposed_at")
    list_filter = ("part", "reagent_type", "disposed_at")
    search_fields = ("item_code", "item_name", "lot_no")
    ordering = ("item_code", "lot_no")


@admin.register(TransactionHistory)
class TransactionHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "tx_type", "item_code", "item_name", "lot_no", "qty", "tx_date", "remaining_stock")
    list_filter = ("tx_type", "part")
    search_fields = ("item_code", "item_name", "lot_no")
    ordering = ("-tx_date", "-id")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_superuser", "is_active", "last_login")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
