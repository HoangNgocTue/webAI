import os
from pathlib import Path
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from fastapi import Request
from dotenv import load_dotenv

load_dotenv()

from .database import SessionLocal, engine
from .models import User, Product, Category, Order, OrderItem, Invoice, SupportTicket
from .admin_utils import authenticate_admin

BASE_DIR = Path(__file__).resolve().parent.parent

# Must match app SessionMiddleware key so /admin/ can read the same session cookie
ADMIN_SECRET = os.getenv("SECRET_KEY", "danang-store-dev-secret-change-in-production")


class StoreAdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        db = SessionLocal()
        try:
            user = authenticate_admin(db, username, password)
            if user:
                request.session.update({"user_id": user.id, "admin_user": user.username, "admin_id": user.id})
                return True
        finally:
            db.close()
        return False

    async def logout(self, request: Request) -> bool:
        request.session.pop("admin_user", None)
        request.session.pop("admin_id", None)
        return True

    async def authenticate(self, request: Request) -> bool:
        return "admin_user" in request.session


class UserAdmin(ModelView, model=User):
    name = "Người dùng"
    name_plural = "Người dùng"
    icon = "fa-solid fa-users"
    column_list = [User.id, User.username, User.email, User.is_staff, User.is_active, User.date_joined]
    column_searchable_list = [User.username, User.email]
    form_excluded_columns = [User.password, User.orders, User.chat_histories, User.shipping_addresses]
    column_details_exclude_list = [User.password]


class CategoryAdmin(ModelView, model=Category):
    name = "Danh mục"
    name_plural = "Danh mục"
    icon = "fa-solid fa-tags"
    column_list = [Category.id, Category.name, Category.slug, Category.is_sub]
    column_searchable_list = [Category.name, Category.slug]
    form_excluded_columns = [Category.products]


class ProductAdmin(ModelView, model=Product):
    name = "Sản phẩm"
    name_plural = "Sản phẩm"
    icon = "fa-solid fa-box"
    column_list = [Product.id, Product.name, Product.price, Product.stock, Product.color]
    column_searchable_list = [Product.name]
    column_sortable_list = [Product.id, Product.name, Product.price, Product.stock]
    form_excluded_columns = [Product.categories, Product.order_items]


class OrderAdmin(ModelView, model=Order):
    name = "Đơn hàng"
    name_plural = "Đơn hàng"
    icon = "fa-solid fa-shopping-cart"
    column_list = [Order.id, Order.customer_id, Order.status, Order.complete, Order.date_order, Order.approved_date]
    column_sortable_list = [Order.id, Order.status, Order.date_order]
    form_excluded_columns = [Order.order_items, Order.shipping_address, Order.invoice]


class InvoiceAdmin(ModelView, model=Invoice):
    name = "Hóa đơn"
    name_plural = "Hóa đơn"
    icon = "fa-solid fa-file-invoice"
    column_list = [Invoice.id, Invoice.order_id, Invoice.customer_id, Invoice.total_amount, Invoice.invoice_date]
    column_sortable_list = [Invoice.id, Invoice.invoice_date]
    form_excluded_columns = [Invoice.order, Invoice.customer]


class SupportTicketAdmin(ModelView, model=SupportTicket):
    name = "Support Ticket"
    name_plural = "Support Tickets"
    icon = "fa-solid fa-ticket"
    column_list = [
        SupportTicket.ticket_id,
        SupportTicket.category,
        SupportTicket.status,
        SupportTicket.customer_email,
        SupportTicket.created_at,
    ]
    column_searchable_list = [SupportTicket.ticket_id, SupportTicket.customer_email, SupportTicket.description]
    column_sortable_list = [SupportTicket.created_at, SupportTicket.status]


def setup_admin(app, engine):
    admin = Admin(
        app,
        engine,
        authentication_backend=StoreAdminAuth(secret_key=ADMIN_SECRET),
        title="Đà Nẵng Store — Admin",
        templates_dir=str(BASE_DIR / "fastapi_templates"),
    )
    admin.add_view(UserAdmin)
    admin.add_view(CategoryAdmin)
    admin.add_view(ProductAdmin)
    admin.add_view(OrderAdmin)
    admin.add_view(InvoiceAdmin)
    admin.add_view(SupportTicketAdmin)
    return admin
