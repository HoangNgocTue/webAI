from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import Order, OrderItem, Product
from ..templates_config import templates

router = APIRouter(tags=["cart"])


@router.get("/cart/", name="cart")
async def cart(request: Request, ctx: BaseContext = Depends(BaseContext)):
    items = []
    order = None
    if ctx.current_user:
        order = (
            ctx.db.query(Order)
            .filter(Order.customer_id == ctx.current_user.id, Order.complete == False)
            .first()
        )
        if order:
            items = order.order_items
    return templates.TemplateResponse(request, "cart.html", ctx.dict(items=items, order=order))


@router.post("/update_item/", name="update_item")
async def update_item(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    product_id = data.get("productId")
    action = data.get("action")
    user_id = request.session["user_id"]
    if action not in {"add", "remove"}:
        raise HTTPException(status_code=400, detail="Invalid cart action")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    order = db.query(Order).filter(Order.customer_id == user_id, Order.complete == False).first()
    if not order:
        order = Order(customer_id=user_id)
        db.add(order)
        db.flush()

    order_item = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id, OrderItem.product_id == product_id)
        .first()
    )
    if not order_item:
        order_item = OrderItem(order_id=order.id, product_id=product_id, quantity=0)
        db.add(order_item)
        db.flush()

    if action == "add":
        order_item.quantity += 1
    elif action == "remove":
        order_item.quantity -= 1

    if order_item.quantity <= 0:
        db.delete(order_item)
        qty = 0
        item_total = 0
    else:
        qty = order_item.quantity
        item_total = float(order_item.get_total)

    db.commit()
    db.refresh(order)

    return JSONResponse(
        {
            "quantity": qty,
            "item_total": item_total,
            "removed": qty == 0,
            "cart_total": float(order.get_cart_total),
            "cart_items": order.get_cart_items,
        }
    )
