from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings


@receiver(pre_save, sender='chatbot.SupportTicket')
def notify_customer_on_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if old.status == instance.status:
        return

    if not instance.customer_email:
        return

    status_labels = {
        'open': 'Chờ xử lý',
        'in_progress': 'Đang xử lý',
        'resolved': 'Đã giải quyết',
    }
    new_status = status_labels.get(instance.status, instance.status)

    subject = f"[Đà Nẵng Store] Ticket {instance.ticket_id} - {new_status}"

    body = f"""Xin chào,

Ticket hỗ trợ của bạn đã được cập nhật:

- Mã ticket: {instance.ticket_id}
- Loại: {instance.get_category_display()}
- Trạng thái mới: {new_status}
"""
    if instance.staff_note:
        body += f"\nGhi chú từ nhân viên:\n{instance.staff_note}\n"

    body += """
Nếu cần thêm hỗ trợ, vui lòng liên hệ:
- Hotline: 0905 123 456
- Địa chỉ: 123 Nguyễn Văn Linh, Đà Nẵng

Trân trọng,
Đà Nẵng Store
"""

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.customer_email],
            fail_silently=False,
        )
        print(f"Email sent for ticket {instance.ticket_id} to {instance.customer_email}")
    except Exception as e:
        print(f"Email send failed for {instance.ticket_id}: {e}")
