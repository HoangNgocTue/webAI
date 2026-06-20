from decimal import Decimal

from fastapi import Request
from sqlalchemy.orm import Session, joinedload

from .models import Order, OrderItem, Product, User


SESSION_CART_KEY = "guest_cart"
CHECKOUT_NEXT_KEY = "post_login_redirect"


class GuestCartItem:
    def __init__(self, product: Product, quantity: int):
        self.id = product.id
        self.product = product
        self.product_id = product.id
        self.quantity = quantity

    @property
    def get_total(self):
        if self.product and self.product.price:
            return Decimal(str(self.product.price)) * self.quantity
        return Decimal("0")


class GuestOrder:
    def __init__(self, items: list[GuestCartItem]):
        self.id = None
        self.order_items = items
        self.complete = False
        self.status = "cart"
        self.transaction_id = None

    @property
    def get_cart_items(self):
        return sum(item.quantity for item in self.order_items)

    @property
    def get_cart_total(self):
        return sum(item.get_total for item in self.order_items)


def _session_cart(request: Request) -> dict[str, int]:
    raw_cart = request.session.get(SESSION_CART_KEY) or {}
    cleaned = {}
    for product_id, quantity in raw_cart.items():
        try:
            pid = str(int(product_id))
            qty = int(quantity)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            cleaned[pid] = qty
    request.session[SESSION_CART_KEY] = cleaned
    return cleaned


def get_guest_cart_items(db: Session, request: Request) -> list[GuestCartItem]:
    cart = _session_cart(request)
    if not cart:
        return []
    ids = [int(product_id) for product_id in cart.keys()]
    products = db.query(Product).filter(Product.id.in_(ids)).all()
    product_map = {product.id: product for product in products}
    return [
        GuestCartItem(product_map[int(product_id)], quantity)
        for product_id, quantity in cart.items()
        if int(product_id) in product_map
    ]


def get_or_create_active_order(db: Session, user: User) -> Order:
    order = db.query(Order).filter(Order.customer_id == user.id, Order.complete == False).first()
    if not order:
        order = Order(customer_id=user.id, complete=False)
        db.add(order)
        db.flush()
    return order


def get_user_cart_items(db: Session, user: User) -> tuple[Order | None, list[OrderItem]]:
    order = db.query(Order).filter(Order.customer_id == user.id, Order.complete == False).first()
    if not order:
        return None, []
    items = (
        db.query(OrderItem)
        .options(joinedload(OrderItem.product))
        .filter(OrderItem.order_id == order.id, OrderItem.quantity > 0, OrderItem.product_id.isnot(None))
        .all()
    )
    return order, items


def get_cart(db: Session, request: Request, user: User | None) -> tuple[Order | GuestOrder | None, list]:
    if user:
        return get_user_cart_items(db, user)
    items = get_guest_cart_items(db, request)
    return (GuestOrder(items) if items else None), items


def update_cart_item(db: Session, request: Request, product: Product, action: str, user: User | None) -> tuple[int, int, Decimal]:
    if user:
        order = get_or_create_active_order(db, user)
        item = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id, OrderItem.product_id == product.id)
            .first()
        )
        if not item:
            item = OrderItem(order_id=order.id, product_id=product.id, quantity=0)
            db.add(item)
            db.flush()
        item.quantity += 1 if action == "add" else -1
        qty = max(item.quantity, 0)
        if item.quantity <= 0:
            db.delete(item)
        db.commit()
        db.refresh(order)
        return qty, order.get_cart_items, order.get_cart_total

    cart = _session_cart(request)
    key = str(product.id)
    cart[key] = int(cart.get(key, 0)) + (1 if action == "add" else -1)
    if cart[key] <= 0:
        cart.pop(key, None)
    request.session[SESSION_CART_KEY] = cart
    items = get_guest_cart_items(db, request)
    order = GuestOrder(items)
    return int(cart.get(key, 0)), order.get_cart_items, order.get_cart_total


def merge_guest_cart_into_user(db: Session, request: Request, user: User):
    cart = _session_cart(request)
    if not cart:
        return
    order = get_or_create_active_order(db, user)
    for product_id, quantity in cart.items():
        product = db.query(Product).filter(Product.id == int(product_id)).first()
        if not product:
            continue
        item = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id, OrderItem.product_id == product.id)
            .first()
        )
        if not item:
            item = OrderItem(order_id=order.id, product_id=product.id, quantity=0)
            db.add(item)
            db.flush()
        item.quantity += int(quantity)
    request.session.pop(SESSION_CART_KEY, None)
    db.commit()
