from sqlalchemy import Column, Integer, String, Boolean, Numeric, Text, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from decimal import Decimal
import uuid
from .database import Base


def _generate_ticket_id():
    return "TKT-" + uuid.uuid4().hex[:6].upper()


# M2M junction table for Product <-> Category (matches Django's naming)
product_category = Table(
    "app_product_category",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("app_product.id")),
    Column("category_id", Integer, ForeignKey("app_category.id")),
)


class User(Base):
    __tablename__ = "auth_user"

    id = Column(Integer, primary_key=True, index=True)
    password = Column(String(128))
    last_login = Column(DateTime, nullable=True)
    is_superuser = Column(Boolean, default=False)
    username = Column(String(150), unique=True, index=True)
    first_name = Column(String(150), default="")
    last_name = Column(String(150), default="")
    email = Column(String(254), default="")
    is_staff = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    date_joined = Column(DateTime, default=func.now())

    orders = relationship("Order", back_populates="customer")
    chat_histories = relationship("ChatHistory", back_populates="user")
    shipping_addresses = relationship("ShippingAddress", back_populates="customer")

    @property
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_authenticated(self):
        return True


class Category(Base):
    __tablename__ = "app_category"

    id = Column(Integer, primary_key=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("app_category.id"), nullable=True)
    is_sub = Column(Boolean, default=False)
    name = Column(String(200))
    slug = Column(String(200), unique=True)

    products = relationship("Product", secondary=product_category, back_populates="categories")


class Product(Base):
    __tablename__ = "app_product"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200))
    price = Column(Numeric(12, 2))
    digital = Column(Boolean, default=False)
    image = Column(String(200), nullable=True)
    detail = Column(Text, nullable=True)
    color = Column(String(20), default="black")
    cpu = Column(String(100), nullable=True)
    gpu = Column(String(100), nullable=True)
    ram = Column(String(50), nullable=True)
    storage = Column(String(50), nullable=True)
    stock = Column(Integer, default=10)

    categories = relationship("Category", secondary=product_category, back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")

    @property
    def ImageURL(self):
        if self.image:
            return f"/images/{self.image}"
        return ""


class Order(Base):
    __tablename__ = "app_order"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("auth_user.id"), nullable=True)
    date_order = Column(DateTime, default=func.now())
    complete = Column(Boolean, default=False)
    transaction_id = Column(String(200), nullable=True)
    approved_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="pending")

    customer = relationship("User", back_populates="orders")
    order_items = relationship("OrderItem", back_populates="order")
    shipping_address = relationship("ShippingAddress", back_populates="order", uselist=False)
    invoice = relationship("Invoice", back_populates="order", uselist=False)

    @property
    def get_cart_items(self):
        return sum(item.quantity for item in self.order_items)

    @property
    def get_cart_total(self):
        return sum(item.get_total for item in self.order_items if item.product)


class OrderItem(Base):
    __tablename__ = "app_orderitem"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("app_product.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("app_order.id"), nullable=True)
    quantity = Column(Integer, default=0)
    date_added = Column(DateTime, default=func.now())

    product = relationship("Product", back_populates="order_items")
    order = relationship("Order", back_populates="order_items")

    @property
    def get_total(self):
        if self.product and self.product.price:
            return Decimal(str(self.product.price)) * self.quantity
        return Decimal("0")


class ShippingAddress(Base):
    __tablename__ = "app_shippingaddress"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("auth_user.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("app_order.id"), nullable=True)
    address = Column(String(200))
    city = Column(String(200))
    state = Column(String(200))
    mobile = Column(String(10))
    date_added = Column(DateTime, default=func.now())

    customer = relationship("User", back_populates="shipping_addresses")
    order = relationship("Order", back_populates="shipping_address")


class Invoice(Base):
    __tablename__ = "app_invoice"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("app_order.id"), unique=True)
    invoice_date = Column(DateTime, default=func.now())
    customer_id = Column(Integer, ForeignKey("auth_user.id"), nullable=True)
    total_amount = Column(Numeric(10, 2))

    order = relationship("Order", back_populates="invoice")
    customer = relationship("User")


class ChatHistory(Base):
    __tablename__ = "chatbot_chathistory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"))
    message = Column(Text)
    reply = Column(Text)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="chat_histories")


class SupportTicket(Base):
    __tablename__ = "chatbot_supportticket"

    CATEGORY_CHOICES = {
        "order_payment": "Đặt hàng / Thanh toán",
        "account": "Tài khoản",
        "cart_product": "Giỏ hàng / Sản phẩm",
        "delivery_warranty": "Giao hàng / Bảo hành",
        "other": "Khác",
    }

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(String(20), unique=True, default=_generate_ticket_id)
    category = Column(String(30), default="other")
    description = Column(Text)
    status = Column(String(20), default="open")
    customer_email = Column(String(254), nullable=True)
    staff_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def get_category_display(self):
        return self.CATEGORY_CHOICES.get(self.category, self.category)
