from django.contrib import admin
from .models import *
from django.utils.timezone import localtime, now

# Tùy chỉnh hiển thị Order trong admin
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'get_local_date_order', 'get_local_approved_date', 'complete', 'transaction_id', 'status')
    list_filter = ('complete', 'status', 'date_order')
    search_fields = ('customer__username', 'transaction_id')
    actions = ['approve_orders', 'reject_orders']  # Thêm các hành động

    # Phương thức để hiển thị thời gian đặt hàng
    def get_local_date_order(self, obj):
        return localtime(obj.date_order).strftime('%d-%m-%Y %H:%M:%S')
    get_local_date_order.short_description = 'Thời gian đặt hàng'

    # Hiển thị thời gian duyệt đơn hàng
    def get_local_approved_date(self, obj):
        if obj.approved_date:
            return localtime(obj.approved_date).strftime('%d-%m-%Y %H:%M:%S')
        return "Chưa duyệt"
    get_local_approved_date.short_description = 'Thời gian duyệt'

    # Hành động duyệt đơn
    @admin.action(description='Duyệt các đơn hàng đã chọn')
    def approve_orders(self, request, queryset):
        updated = 0
        for order in queryset:
            order.status = 'approved'
            order.complete = True
            order.approved_date = now()
            if not order.transaction_id:
                order.transaction_id = f"APPROVED-{order.id}-{int(order.approved_date.timestamp())}"
            order.save()
            Invoice.objects.update_or_create(
                order=order,
                defaults={
                    "customer": order.customer,
                    "total_amount": order.get_cart_total,
                },
            )
            updated += 1
        self.message_user(request, f'{updated} đơn hàng đã được duyệt.')

    # Hành động từ chối đơn
    @admin.action(description='Từ chối các đơn hàng đã chọn')
    def reject_orders(self, request, queryset):
        updated = queryset.update(status='canceled', approved_date=None)  # Đặt trạng thái "canceled"
        self.message_user(request, f'{updated} đơn hàng đã bị từ chối.')

# Tùy chỉnh hiển thị OrderItem trong admin
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'order', 'quantity', 'get_local_date_added')

    # Phương thức tùy chỉnh để hiển thị thời gian thêm vào đơn hàng
    def get_local_date_added(self, obj):
        return localtime(obj.date_added).strftime('%d-%m-%Y %H:%M:%S')
    get_local_date_added.short_description = 'Thời gian thêm vào'

@admin.register(ShippingAddress)
class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'order', 'address', 'city', 'state', 'mobile', 'get_local_date_added')
    search_fields = ('customer__username', 'address', 'city', 'state', 'mobile', 'order__id')
    list_filter = ('city', 'state', 'date_added')

    def get_local_date_added(self, obj):
        return localtime(obj.date_added).strftime('%d-%m-%Y %H:%M:%S')
    get_local_date_added.short_description = 'Thời gian tạo'


# Các model khác vẫn giữ nguyên
admin.site.register(Product)
admin.site.register(Category)
