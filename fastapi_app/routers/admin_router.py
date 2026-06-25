import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import func, extract

from ..dependencies import BaseContext
from ..database import SessionLocal
from ..models import Category, Invoice, User, Order, OrderItem, Product, ShippingAddress, SupportTicket
from ..auth import check_django_password, make_django_password
from ..email_service import _send
from ..templates_config import templates

router = APIRouter(prefix="/quan-tri", tags=["admin_panel"])
legacy_router = APIRouter(tags=["admin_legacy_redirects"])

CATEGORY_LABELS = {
    "order_payment": "Đặt hàng / Thanh toán",
    "account": "Tài khoản",
    "cart_product": "Giỏ hàng / Sản phẩm",
    "delivery_warranty": "Giao hàng / Bảo hành",
    "other": "Khác",
}

STATUS_LABELS = {
    "open": ("Chờ xử lý", "#f97316"),
    "in_progress": ("Đang xử lý", "#3b82f6"),
    "resolved": ("Đã giải quyết", "#22c55e"),
    "closed": ("Đã đóng", "#94a3b8"),
}


def _require_admin(request: Request, ctx: BaseContext):
    if not ctx.current_user or not (ctx.current_user.is_staff or ctx.current_user.is_superuser):
        return RedirectResponse("/quan-tri/login/", status_code=302)
    # Keep admin identity in session for the custom admin panel.
    if "admin_user" not in request.session:
        request.session["admin_user"] = ctx.current_user.username
        request.session["admin_id"] = ctx.current_user.id
    return None


# ─── Admin Login ──────────────────────────────────────────────────────────────

@router.get("/login/", name="admin_login")
async def admin_login_get(request: Request, ctx: BaseContext = Depends(BaseContext)):
    if ctx.current_user and (ctx.current_user.is_staff or ctx.current_user.is_superuser):
        return RedirectResponse("/quan-tri/", status_code=302)
    return templates.TemplateResponse(request, "admin_login.html", {"request": request, "error": None})


@router.post("/login/", name="admin_login_post")
async def admin_login_post(request: Request, ctx: BaseContext = Depends(BaseContext)):
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.username == username, User.is_active == True)
            .first()
        )
        is_admin = user and (user.is_staff or user.is_superuser)
        if is_admin and check_django_password(password, user.password):
            request.session["user_id"] = user.id
            request.session["admin_user"] = user.username
            request.session["admin_id"] = user.id
            user.last_login = datetime.utcnow()
            db.commit()
            return RedirectResponse("/quan-tri/", status_code=302)
    finally:
        db.close()

    return templates.TemplateResponse(
        request, "admin_login.html",
        {"request": request, "error": "Tên đăng nhập / mật khẩu không đúng hoặc tài khoản không có quyền admin."}
    )

def _open_count(db) -> int:
    return db.query(func.count(SupportTicket.id)).filter(SupportTicket.status == "open").scalar() or 0


def _fmt_money(value) -> str:
    try:
        return f"{int(float(value or 0)):,.0f}".replace(",", ".") + "đ"
    except Exception:
        return str(value or "")


def _fmt_date(value) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "—"


# ─── Dashboard ───────────────────────────────────────────────────────────────

def _render_admin_list(request: Request, ctx: BaseContext, *, title: str, icon: str, active_page: str, columns: list[str], rows: list[list[str]], create_url: str | None = None):
    return templates.TemplateResponse(request, "admin_list.html", ctx.dict(
        title=title,
        icon=icon,
        active_page=active_page,
        columns=columns,
        rows=rows,
        create_url=create_url,
        open_ticket_count=_open_count(ctx.db),
    ))


def _admin_redirect(path: str):
    return RedirectResponse(path, status_code=302)


def _form_bool(form, key: str) -> bool:
    return form.get(key) in {"1", "true", "on", "yes"}


def _form_int(form, key: str):
    value = str(form.get(key, "")).strip()
    return int(value) if value else None


def _form_decimal(form, key: str) -> Decimal:
    raw = str(form.get(key, "0")).strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(raw or "0")
    except Exception:
        return Decimal("0")


def _actions(edit_url: str, delete_url: str, label: str) -> str:
    return f"""
    <div style="display:flex;gap:8px;align-items:center;white-space:nowrap;">
      <a href="{edit_url}" class="adm-btn adm-btn-ghost" style="padding:6px 10px;font-size:0.78rem;">Sửa</a>
      <form method="post" action="{delete_url}" style="margin:0;"
            onsubmit="return confirm('Xóa {label}?');">
        <button type="submit" class="adm-btn" style="padding:6px 10px;font-size:0.78rem;background:#fee2e2;color:#b91c1c;">Xóa</button>
      </form>
    </div>
    """


def _render_form(request: Request, ctx: BaseContext, *, title: str, icon: str, active_page: str, action_url: str, back_url: str, fields: list[dict], submit_label: str = "Lưu"):
    return templates.TemplateResponse(request, "admin_form.html", ctx.dict(
        title=title,
        icon=icon,
        active_page=active_page,
        action_url=action_url,
        back_url=back_url,
        fields=fields,
        submit_label=submit_label,
        open_ticket_count=_open_count(ctx.db),
    ))


@legacy_router.get("/admin/")
@legacy_router.get("/admin/{path:path}")
async def legacy_admin_redirect(path: str = ""):
    return RedirectResponse("/quan-tri/", status_code=302)


@router.get("/", name="admin_dashboard")
async def dashboard(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    db = ctx.db
    now = datetime.utcnow()

    # Stats
    total_orders     = db.query(func.count(Order.id)).scalar() or 0
    total_customers  = db.query(func.count(User.id)).filter(User.is_staff == False).scalar() or 0
    total_products   = db.query(func.count(Product.id)).scalar() or 0
    total_stock      = db.query(func.sum(Product.stock)).scalar() or 0
    total_revenue    = db.query(func.sum(OrderItem.quantity * Product.price))\
                         .join(Product, OrderItem.product_id == Product.id)\
                         .join(Order, OrderItem.order_id == Order.id)\
                         .filter(Order.complete == True).scalar() or Decimal("0")
    total_revenue    = int(total_revenue)

    # Order status
    orders_pending   = db.query(func.count(Order.id)).filter(Order.status == "pending", Order.complete == False).scalar() or 0
    orders_approved  = db.query(func.count(Order.id)).filter(Order.status == "approved").scalar() or 0
    orders_canceled  = db.query(func.count(Order.id)).filter(Order.status == "canceled").scalar() or 0

    # Recent orders
    recent_orders = (
        db.query(Order, User.username)
        .outerjoin(User, Order.customer_id == User.id)
        .order_by(Order.date_order.desc())
        .limit(8)
        .all()
    )

    # Top products
    top_products = (
        db.query(Product.id, Product.name, func.sum(OrderItem.quantity).label("sold"))
        .join(OrderItem, Product.id == OrderItem.product_id)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )

    # Revenue last 12 months
    months_data = []
    for i in range(11, -1, -1):
        target = now - timedelta(days=i * 30)
        rev = db.query(func.sum(OrderItem.quantity * Product.price))\
                .join(Product, OrderItem.product_id == Product.id)\
                .join(Order, OrderItem.order_id == Order.id)\
                .filter(
                    Order.complete == True,
                    extract("year",  Order.date_order) == target.year,
                    extract("month", Order.date_order) == target.month,
                ).scalar() or Decimal("0")
        months_data.append({"month": target.strftime("%m/%Y"), "revenue": int(rev)})

    # Open tickets
    open_tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.status == "open")
        .order_by(SupportTicket.created_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(request, "admin_dashboard.html", ctx.dict(
        total_revenue=f"{total_revenue:,.0f}".replace(",", "."),
        total_orders=total_orders,
        total_customers=total_customers,
        total_products=total_products,
        total_stock=total_stock,
        orders_pending=orders_pending,
        orders_approved=orders_approved,
        orders_canceled=orders_canceled,
        recent_orders=recent_orders,
        top_products=top_products,
        months_data=json.dumps(months_data),
        open_tickets=open_tickets,
        open_ticket_count=len(open_tickets),
        category_labels=CATEGORY_LABELS,
        active_page="dashboard",
    ))


# ─── Ticket List ─────────────────────────────────────────────────────────────

@router.get("/orders/", name="admin_orders")
async def admin_orders(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    rows = []
    orders = (
        ctx.db.query(Order, User.username)
        .outerjoin(User, Order.customer_id == User.id)
        .order_by(Order.date_order.desc())
        .all()
    )
    for order, username in orders:
        rows.append([
            f"#{order.id}",
            username or "Khách vãng lai",
            order.status or "pending",
            order.payment_status or "unpaid",
            _fmt_money(order.get_cart_total),
            _fmt_date(order.date_order),
            _actions(f"/quan-tri/orders/{order.id}/edit/", f"/quan-tri/orders/{order.id}/delete/", f"don hang #{order.id}"),
        ])
    return _render_admin_list(
        request, ctx,
        title="Đơn hàng",
        icon="🛒",
        active_page="orders",
        columns=["Mã đơn", "Khách hàng", "Trạng thái", "Thanh toán", "Tổng tiền", "Ngày đặt", "Thao tác"],
        rows=rows,
        create_url="/quan-tri/orders/new/",
    )


@router.get("/products/", name="admin_products")
async def admin_products(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    rows = []
    for product in ctx.db.query(Product).order_by(Product.id.desc()).all():
        rows.append([
            f"#{product.id}",
            product.name or "",
            _fmt_money(product.price),
            str(product.stock or 0),
            ", ".join(category.name for category in product.categories) or "Chưa phân loại",
            _actions(f"/quan-tri/products/{product.id}/edit/", f"/quan-tri/products/{product.id}/delete/", product.name or f"san pham #{product.id}"),
        ])
    return _render_admin_list(
        request, ctx,
        title="Sản phẩm",
        icon="📦",
        active_page="products",
        columns=["ID", "Tên sản phẩm", "Giá", "Tồn kho", "Danh mục", "Thao tác"],
        rows=rows,
        create_url="/quan-tri/products/new/",
    )


@router.get("/users/", name="admin_users")
async def admin_users(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    rows = []
    for user in ctx.db.query(User).order_by(User.id.desc()).all():
        role = "Superuser" if user.is_superuser else ("Staff" if user.is_staff else "Khách hàng")
        rows.append([
            f"#{user.id}",
            user.username or "",
            user.email or "",
            role,
            "Hoạt động" if user.is_active else "Đã khóa",
            _fmt_date(user.date_joined),
            _actions(f"/quan-tri/users/{user.id}/edit/", f"/quan-tri/users/{user.id}/delete/", user.username or f"user #{user.id}"),
        ])
    return _render_admin_list(
        request, ctx,
        title="Người dùng",
        icon="👥",
        active_page="users",
        columns=["ID", "Username", "Email", "Vai trò", "Trạng thái", "Ngày tham gia", "Thao tác"],
        rows=rows,
        create_url="/quan-tri/users/new/",
    )


@router.get("/categories/", name="admin_categories")
async def admin_categories(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    rows = []
    for category in ctx.db.query(Category).order_by(Category.id.desc()).all():
        rows.append([
            f"#{category.id}",
            category.name or "",
            category.slug or "",
            "Danh mục con" if category.is_sub else "Danh mục chính",
            str(len(category.products)),
            _actions(f"/quan-tri/categories/{category.id}/edit/", f"/quan-tri/categories/{category.id}/delete/", category.name or f"danh muc #{category.id}"),
        ])
    return _render_admin_list(
        request, ctx,
        title="Danh mục",
        icon="🏷️",
        active_page="categories",
        columns=["ID", "Tên danh mục", "Slug", "Loại", "Số sản phẩm", "Thao tác"],
        rows=rows,
        create_url="/quan-tri/categories/new/",
    )


@router.get("/invoices/", name="admin_invoices")
async def admin_invoices(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    rows = []
    invoices = (
        ctx.db.query(Invoice, User.username)
        .outerjoin(User, Invoice.customer_id == User.id)
        .order_by(Invoice.invoice_date.desc())
        .all()
    )
    for invoice, username in invoices:
        rows.append([
            f"#{invoice.id}",
            f"#{invoice.order_id}" if invoice.order_id else "—",
            username or "Khách vãng lai",
            _fmt_money(invoice.total_amount),
            _fmt_date(invoice.invoice_date),
            _actions(f"/quan-tri/invoices/{invoice.id}/edit/", f"/quan-tri/invoices/{invoice.id}/delete/", f"hoa don #{invoice.id}"),
        ])
    return _render_admin_list(
        request, ctx,
        title="Hóa đơn",
        icon="🧾",
        active_page="invoices",
        columns=["Mã hóa đơn", "Mã đơn", "Khách hàng", "Tổng tiền", "Ngày lập", "Thao tác"],
        rows=rows,
        create_url="/quan-tri/invoices/new/",
    )


def _category_options(ctx: BaseContext, include_blank: bool = False):
    options = [{"value": "", "label": "Khong chon"}] if include_blank else []
    options.extend({"value": c.id, "label": c.name or f"#{c.id}"} for c in ctx.db.query(Category).order_by(Category.name.asc()).all())
    return options


def _user_options(ctx: BaseContext, include_blank: bool = True):
    options = [{"value": "", "label": "Khach vang lai"}] if include_blank else []
    options.extend({"value": u.id, "label": f"{u.username} - {u.email or 'no email'}"} for u in ctx.db.query(User).order_by(User.username.asc()).all())
    return options


def _order_options(ctx: BaseContext, include_blank: bool = True):
    options = [{"value": "", "label": "Khong gan don"}] if include_blank else []
    options.extend({"value": o.id, "label": f"Don #{o.id} - {_fmt_date(o.date_order)}"} for o in ctx.db.query(Order).order_by(Order.id.desc()).all())
    return options


def _product_fields(ctx: BaseContext, product: Product | None = None):
    product = product or Product(price=0, stock=10, digital=False)
    selected = [c.id for c in product.categories] if product.id else []
    return [
        {"name": "name", "label": "Ten san pham", "type": "text", "value": product.name},
        {"name": "price", "label": "Gia", "type": "number", "step": "1000", "value": int(product.price or 0)},
        {"name": "stock", "label": "Ton kho", "type": "number", "value": product.stock or 0},
        {"name": "image", "label": "Anh san pham", "type": "text", "value": product.image},
        {"name": "color", "label": "Mau sac", "type": "text", "value": product.color or "black"},
        {"name": "cpu", "label": "CPU", "type": "text", "value": product.cpu},
        {"name": "gpu", "label": "GPU", "type": "text", "value": product.gpu},
        {"name": "ram", "label": "RAM", "type": "text", "value": product.ram},
        {"name": "storage", "label": "Bo nho", "type": "text", "value": product.storage},
        {"name": "digital", "label": "San pham digital", "type": "checkbox", "checked": bool(product.digital)},
        {"name": "category_ids", "label": "Danh muc", "type": "multiselect", "options": _category_options(ctx), "selected_values": selected},
        {"name": "detail", "label": "Mo ta / thong tin san pham", "type": "textarea", "rows": 6, "value": product.detail},
    ]


@router.get("/products/new/", name="admin_product_new")
async def product_new(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    return _render_form(request, ctx, title="Them san pham", icon="📦", active_page="products", action_url="/quan-tri/products/new/", back_url="/quan-tri/products/", fields=_product_fields(ctx), submit_label="Them san pham")


@router.post("/products/new/")
async def product_create(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    product = Product()
    return await _save_product(request, ctx, product)


@router.get("/products/{product_id}/edit/", name="admin_product_edit")
async def product_edit(product_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    product = ctx.db.get(Product, product_id)
    if not product:
        return _admin_redirect("/quan-tri/products/")
    return _render_form(request, ctx, title=f"Sua san pham #{product.id}", icon="📦", active_page="products", action_url=f"/quan-tri/products/{product.id}/edit/", back_url="/quan-tri/products/", fields=_product_fields(ctx, product))


@router.post("/products/{product_id}/edit/")
async def product_update(product_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    product = ctx.db.get(Product, product_id)
    if not product:
        return _admin_redirect("/quan-tri/products/")
    return await _save_product(request, ctx, product)


async def _save_product(request: Request, ctx: BaseContext, product: Product):
    form = await request.form()
    product.name = form.get("name", "").strip()
    product.price = _form_decimal(form, "price")
    product.stock = _form_int(form, "stock") or 0
    product.image = form.get("image", "").strip() or None
    product.detail = form.get("detail", "").strip() or None
    product.color = form.get("color", "").strip() or "black"
    product.cpu = form.get("cpu", "").strip() or None
    product.gpu = form.get("gpu", "").strip() or None
    product.ram = form.get("ram", "").strip() or None
    product.storage = form.get("storage", "").strip() or None
    product.digital = _form_bool(form, "digital")
    category_ids = [int(v) for v in form.getlist("category_ids") if str(v).isdigit()]
    product.categories = ctx.db.query(Category).filter(Category.id.in_(category_ids)).all() if category_ids else []
    ctx.db.add(product)
    ctx.db.commit()
    return _admin_redirect("/quan-tri/products/")


@router.post("/products/{product_id}/delete/")
async def product_delete(product_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    product = ctx.db.get(Product, product_id)
    if product:
        product.categories = []
        for item in ctx.db.query(OrderItem).filter(OrderItem.product_id == product.id).all():
            item.product_id = None
        ctx.db.delete(product)
        ctx.db.commit()
    return _admin_redirect("/quan-tri/products/")


def _category_fields(ctx: BaseContext, category: Category | None = None):
    category = category or Category(is_sub=False)
    return [
        {"name": "name", "label": "Ten danh muc", "type": "text", "value": category.name},
        {"name": "slug", "label": "Slug", "type": "text", "value": category.slug},
        {"name": "sub_category_id", "label": "Danh muc cha", "type": "select", "value": category.sub_category_id or "", "options": [o for o in _category_options(ctx, True) if o["value"] != getattr(category, "id", None)]},
        {"name": "is_sub", "label": "La danh muc con", "type": "checkbox", "checked": bool(category.is_sub)},
    ]


@router.get("/categories/new/", name="admin_category_new")
async def category_new(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    return _render_form(request, ctx, title="Them danh muc", icon="🏷️", active_page="categories", action_url="/quan-tri/categories/new/", back_url="/quan-tri/categories/", fields=_category_fields(ctx), submit_label="Them danh muc")


@router.post("/categories/new/")
async def category_create(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    category = Category()
    return await _save_category(request, ctx, category)


@router.get("/categories/{category_id}/edit/", name="admin_category_edit")
async def category_edit(category_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    category = ctx.db.get(Category, category_id)
    if not category:
        return _admin_redirect("/quan-tri/categories/")
    return _render_form(request, ctx, title=f"Sua danh muc #{category.id}", icon="🏷️", active_page="categories", action_url=f"/quan-tri/categories/{category.id}/edit/", back_url="/quan-tri/categories/", fields=_category_fields(ctx, category))


@router.post("/categories/{category_id}/edit/")
async def category_update(category_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    category = ctx.db.get(Category, category_id)
    if not category:
        return _admin_redirect("/quan-tri/categories/")
    return await _save_category(request, ctx, category)


async def _save_category(request: Request, ctx: BaseContext, category: Category):
    form = await request.form()
    category.name = form.get("name", "").strip()
    category.slug = form.get("slug", "").strip()
    category.sub_category_id = _form_int(form, "sub_category_id")
    category.is_sub = _form_bool(form, "is_sub") or bool(category.sub_category_id)
    ctx.db.add(category)
    ctx.db.commit()
    return _admin_redirect("/quan-tri/categories/")


@router.post("/categories/{category_id}/delete/")
async def category_delete(category_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    category = ctx.db.get(Category, category_id)
    if category:
        category.products = []
        for child in ctx.db.query(Category).filter(Category.sub_category_id == category.id).all():
            child.sub_category_id = None
            child.is_sub = False
        ctx.db.delete(category)
        ctx.db.commit()
    return _admin_redirect("/quan-tri/categories/")


def _user_fields(user: User | None = None):
    user = user or User(is_active=True, is_staff=False, is_superuser=False)
    return [
        {"name": "username", "label": "Username", "type": "text", "value": user.username},
        {"name": "email", "label": "Email", "type": "email", "value": user.email},
        {"name": "first_name", "label": "Ho", "type": "text", "value": user.first_name},
        {"name": "last_name", "label": "Ten", "type": "text", "value": user.last_name},
        {"name": "password", "label": "Mat khau moi (bo trong neu khong doi)", "type": "password", "value": ""},
        {"name": "is_active", "label": "Dang hoat dong", "type": "checkbox", "checked": bool(user.is_active)},
        {"name": "is_staff", "label": "Nhan vien quan tri", "type": "checkbox", "checked": bool(user.is_staff)},
        {"name": "is_superuser", "label": "Superuser", "type": "checkbox", "checked": bool(user.is_superuser)},
    ]


@router.get("/users/new/", name="admin_user_new")
async def user_new(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    return _render_form(request, ctx, title="Them nguoi dung", icon="👥", active_page="users", action_url="/quan-tri/users/new/", back_url="/quan-tri/users/", fields=_user_fields(), submit_label="Them nguoi dung")


@router.post("/users/new/")
async def user_create(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    user = User(date_joined=datetime.utcnow())
    return await _save_user(request, ctx, user)


@router.get("/users/{user_id}/edit/", name="admin_user_edit")
async def user_edit(user_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    user = ctx.db.get(User, user_id)
    if not user:
        return _admin_redirect("/quan-tri/users/")
    return _render_form(request, ctx, title=f"Sua nguoi dung #{user.id}", icon="👥", active_page="users", action_url=f"/quan-tri/users/{user.id}/edit/", back_url="/quan-tri/users/", fields=_user_fields(user))


@router.post("/users/{user_id}/edit/")
async def user_update(user_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    user = ctx.db.get(User, user_id)
    if not user:
        return _admin_redirect("/quan-tri/users/")
    return await _save_user(request, ctx, user)


async def _save_user(request: Request, ctx: BaseContext, user: User):
    form = await request.form()
    user.username = form.get("username", "").strip()
    user.email = form.get("email", "").strip()
    user.first_name = form.get("first_name", "").strip()
    user.last_name = form.get("last_name", "").strip()
    password = form.get("password", "").strip()
    if password:
        user.password = make_django_password(password)
    elif not user.password:
        user.password = make_django_password("123")
    user.is_active = _form_bool(form, "is_active")
    user.is_staff = _form_bool(form, "is_staff")
    user.is_superuser = _form_bool(form, "is_superuser")
    ctx.db.add(user)
    ctx.db.commit()
    return _admin_redirect("/quan-tri/users/")


@router.post("/users/{user_id}/delete/")
async def user_delete(user_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    if ctx.current_user and ctx.current_user.id == user_id:
        return _admin_redirect("/quan-tri/users/")
    user = ctx.db.get(User, user_id)
    if user:
        for order in ctx.db.query(Order).filter(Order.customer_id == user.id).all():
            order.customer_id = None
        for invoice in ctx.db.query(Invoice).filter(Invoice.customer_id == user.id).all():
            invoice.customer_id = None
        for address in ctx.db.query(ShippingAddress).filter(ShippingAddress.customer_id == user.id).all():
            address.customer_id = None
        ctx.db.delete(user)
        ctx.db.commit()
    return _admin_redirect("/quan-tri/users/")


def _order_fields(ctx: BaseContext, order: Order | None = None):
    order = order or Order(status="pending", payment_status="unpaid", complete=False)
    return [
        {"name": "customer_id", "label": "Khach hang", "type": "select", "value": order.customer_id or "", "options": _user_options(ctx, True)},
        {"name": "status", "label": "Trang thai don", "type": "select", "value": order.status or "pending", "options": [
            {"value": "pending", "label": "Cho xu ly"},
            {"value": "approved", "label": "Da duyet"},
            {"value": "canceled", "label": "Da huy"},
        ]},
        {"name": "payment_method", "label": "Phuong thuc thanh toan", "type": "select", "value": order.payment_method or "cod", "options": [
            {"value": "cod", "label": "COD"},
            {"value": "vnpay", "label": "VNPAY"},
            {"value": "momo", "label": "MoMo"},
        ]},
        {"name": "payment_status", "label": "Trang thai thanh toan", "type": "select", "value": order.payment_status or "unpaid", "options": [
            {"value": "unpaid", "label": "Chua thanh toan"},
            {"value": "paid", "label": "Da thanh toan"},
            {"value": "failed", "label": "That bai"},
        ]},
        {"name": "transaction_id", "label": "Ma giao dich", "type": "text", "value": order.transaction_id},
        {"name": "payment_ref", "label": "Ma tham chieu thanh toan", "type": "text", "value": order.payment_ref},
        {"name": "complete", "label": "Don hang da hoan tat", "type": "checkbox", "checked": bool(order.complete)},
    ]


@router.get("/orders/new/", name="admin_order_new")
async def order_new(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    return _render_form(request, ctx, title="Them don hang", icon="🛒", active_page="orders", action_url="/quan-tri/orders/new/", back_url="/quan-tri/orders/", fields=_order_fields(ctx), submit_label="Them don hang")


@router.post("/orders/new/")
async def order_create(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    order = Order(date_order=datetime.utcnow())
    return await _save_order(request, ctx, order)


@router.get("/orders/{order_id}/edit/", name="admin_order_edit")
async def order_edit(order_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    order = ctx.db.get(Order, order_id)
    if not order:
        return _admin_redirect("/quan-tri/orders/")
    return _render_form(request, ctx, title=f"Sua don hang #{order.id}", icon="🛒", active_page="orders", action_url=f"/quan-tri/orders/{order.id}/edit/", back_url="/quan-tri/orders/", fields=_order_fields(ctx, order))


@router.post("/orders/{order_id}/edit/")
async def order_update(order_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    order = ctx.db.get(Order, order_id)
    if not order:
        return _admin_redirect("/quan-tri/orders/")
    return await _save_order(request, ctx, order)


async def _save_order(request: Request, ctx: BaseContext, order: Order):
    form = await request.form()
    order.customer_id = _form_int(form, "customer_id")
    order.status = form.get("status", "pending")
    order.payment_method = form.get("payment_method", "cod")
    order.payment_status = form.get("payment_status", "unpaid")
    order.transaction_id = form.get("transaction_id", "").strip() or None
    order.payment_ref = form.get("payment_ref", "").strip() or None
    order.complete = _form_bool(form, "complete")
    if order.status == "approved" and not order.approved_date:
        order.approved_date = datetime.utcnow()
    ctx.db.add(order)
    ctx.db.commit()
    return _admin_redirect("/quan-tri/orders/")


@router.post("/orders/{order_id}/delete/")
async def order_delete(order_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    order = ctx.db.get(Order, order_id)
    if order:
        for item in ctx.db.query(OrderItem).filter(OrderItem.order_id == order.id).all():
            ctx.db.delete(item)
        invoice = ctx.db.query(Invoice).filter(Invoice.order_id == order.id).first()
        if invoice:
            ctx.db.delete(invoice)
        address = ctx.db.query(ShippingAddress).filter(ShippingAddress.order_id == order.id).first()
        if address:
            ctx.db.delete(address)
        ctx.db.delete(order)
        ctx.db.commit()
    return _admin_redirect("/quan-tri/orders/")


def _invoice_fields(ctx: BaseContext, invoice: Invoice | None = None):
    invoice = invoice or Invoice(total_amount=0)
    return [
        {"name": "order_id", "label": "Don hang", "type": "select", "value": invoice.order_id or "", "options": _order_options(ctx, True)},
        {"name": "customer_id", "label": "Khach hang", "type": "select", "value": invoice.customer_id or "", "options": _user_options(ctx, True)},
        {"name": "total_amount", "label": "Tong tien", "type": "number", "step": "1000", "value": int(invoice.total_amount or 0)},
    ]


@router.get("/invoices/new/", name="admin_invoice_new")
async def invoice_new(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    return _render_form(request, ctx, title="Them hoa don", icon="🧾", active_page="invoices", action_url="/quan-tri/invoices/new/", back_url="/quan-tri/invoices/", fields=_invoice_fields(ctx), submit_label="Them hoa don")


@router.post("/invoices/new/")
async def invoice_create(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    invoice = Invoice(invoice_date=datetime.utcnow())
    return await _save_invoice(request, ctx, invoice)


@router.get("/invoices/{invoice_id}/edit/", name="admin_invoice_edit")
async def invoice_edit(invoice_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    invoice = ctx.db.get(Invoice, invoice_id)
    if not invoice:
        return _admin_redirect("/quan-tri/invoices/")
    return _render_form(request, ctx, title=f"Sua hoa don #{invoice.id}", icon="🧾", active_page="invoices", action_url=f"/quan-tri/invoices/{invoice.id}/edit/", back_url="/quan-tri/invoices/", fields=_invoice_fields(ctx, invoice))


@router.post("/invoices/{invoice_id}/edit/")
async def invoice_update(invoice_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    invoice = ctx.db.get(Invoice, invoice_id)
    if not invoice:
        return _admin_redirect("/quan-tri/invoices/")
    return await _save_invoice(request, ctx, invoice)


async def _save_invoice(request: Request, ctx: BaseContext, invoice: Invoice):
    form = await request.form()
    invoice.order_id = _form_int(form, "order_id")
    invoice.customer_id = _form_int(form, "customer_id")
    invoice.total_amount = _form_decimal(form, "total_amount")
    ctx.db.add(invoice)
    ctx.db.commit()
    return _admin_redirect("/quan-tri/invoices/")


@router.post("/invoices/{invoice_id}/delete/")
async def invoice_delete(invoice_id: int, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect
    invoice = ctx.db.get(Invoice, invoice_id)
    if invoice:
        ctx.db.delete(invoice)
        ctx.db.commit()
    return _admin_redirect("/quan-tri/invoices/")


@router.get("/tickets/", name="admin_tickets")
async def ticket_list(request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    status_filter = request.query_params.get("status", "")
    q = ctx.db.query(SupportTicket).order_by(SupportTicket.created_at.desc())
    if status_filter:
        q = q.filter(SupportTicket.status == status_filter)
    tickets = q.all()

    return templates.TemplateResponse(request, "admin_tickets.html", ctx.dict(
        tickets=tickets,
        status_filter=status_filter,
        category_labels=CATEGORY_LABELS,
        status_labels=STATUS_LABELS,
        open_ticket_count=_open_count(ctx.db),
        active_page="tickets",
    ))


# ─── Ticket Detail + Reply ────────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}/", name="admin_ticket_detail")
async def ticket_detail(ticket_id: str, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    ticket = ctx.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not ticket:
        return RedirectResponse("/quan-tri/tickets/", status_code=302)

    return templates.TemplateResponse(request, "admin_ticket_detail.html", ctx.dict(
        ticket=ticket,
        category_labels=CATEGORY_LABELS,
        status_labels=STATUS_LABELS,
        open_ticket_count=_open_count(ctx.db),
        active_page="tickets",
        success=False,
        error=None,
    ))


@router.post("/tickets/{ticket_id}/reply/", name="admin_ticket_reply")
async def ticket_reply(ticket_id: str, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    ticket = ctx.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not ticket:
        return RedirectResponse("/quan-tri/tickets/", status_code=302)

    form = await request.form()
    reply_body  = form.get("reply_body", "").strip()
    new_status  = form.get("new_status", ticket.status)
    admin_name  = ctx.current_user.username if ctx.current_user else "Kỹ thuật viên"

    error = None
    success = False

    if not reply_body:
        error = "Vui lòng nhập nội dung phản hồi."
    elif not ticket.customer_email:
        error = "Ticket này không có email khách hàng."
    else:
        # Update ticket
        ticket.status = new_status
        note_line = f"\n\n[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')} - {admin_name}]:\n{reply_body}"
        ticket.staff_note = (ticket.staff_note or "") + note_line
        ticket.updated_at = datetime.utcnow()
        ctx.db.commit()

        # Send HTML email reply to customer
        cat_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
        body_html = f"""
        <h2>Phản hồi từ Kỹ thuật viên Đà Nẵng Store</h2>
        <p>Xin chào! Chúng tôi đã xem xét yêu cầu hỗ trợ của bạn và có phản hồi như sau:</p>
        <div class="info-box">
          <div class="row"><span class="label">Mã ticket</span><span class="value">{ticket.ticket_id}</span></div>
          <div class="row"><span class="label">Loại vấn đề</span><span class="value">{cat_label}</span></div>
          <div class="row"><span class="label">Trạng thái</span>
            <span class="value" style="color:{'#22c55e' if new_status == 'resolved' else '#3b82f6'};">
              {STATUS_LABELS.get(new_status, (new_status,))[0]}
            </span>
          </div>
        </div>
        <p style="margin:16px 0 6px;font-weight:600;font-size:0.9rem;color:#374151;">Nội dung phản hồi:</p>
        <div class="desc-box">{reply_body}</div>
        <p style="margin-top:20px;font-size:0.88rem;color:#64748b;">
          Nếu cần hỗ trợ thêm, vui lòng gửi yêu cầu mới tại website hoặc gọi hotline <strong>0905 123 456</strong>.
        </p>
        """
        ok = _send(
            to_email=ticket.customer_email,
            subject=f"[Đà Nẵng Store] Phản hồi ticket {ticket.ticket_id}",
            body_html=body_html,
        )
        if ok:
            success = True
        else:
            error = "Gửi email thất bại — kiểm tra cấu hình Gmail trong .env"

    return templates.TemplateResponse(request, "admin_ticket_detail.html", ctx.dict(
        ticket=ticket,
        category_labels=CATEGORY_LABELS,
        status_labels=STATUS_LABELS,
        open_ticket_count=_open_count(ctx.db),
        active_page="tickets",
        success=success,
        error=error,
    ))


@router.post("/tickets/{ticket_id}/status/", name="admin_ticket_status")
async def ticket_status(ticket_id: str, request: Request, ctx: BaseContext = Depends(BaseContext)):
    redirect = _require_admin(request, ctx)
    if redirect:
        return redirect

    form = await request.form()
    new_status = form.get("status", "open")
    ticket = ctx.db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if ticket:
        ticket.status = new_status
        ticket.updated_at = datetime.utcnow()
        ctx.db.commit()

    return RedirectResponse(f"/quan-tri/tickets/{ticket_id}/", status_code=302)
