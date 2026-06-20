from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import Order, OrderItem, Product
from ..cart_utils import get_cart, update_cart_item
from ..templates_config import templates

router = APIRouter(tags=["cart"])


@router.get("/cart/", name="cart")
async def cart(request: Request, ctx: BaseContext = Depends(BaseContext)):
    order, items = get_cart(ctx.db, request, ctx.current_user)
    return templates.TemplateResponse(request, "cart.html", ctx.dict(items=items, order=order))


@router.post("/update_item/", name="update_item")
async def update_item(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    product_id = data.get("productId")
    action = data.get("action")
    if action not in {"add", "remove"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    user = None
    user_id = request.session.get("user_id")
    if user_id:
        from ..models import User
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()

    qty, cart_items, cart_total = update_cart_item(db, request, product, action, user)
    return JSONResponse(
        {
            "quantity": qty,
            "cart_total": float(cart_total),
            "cart_items": cart_items,
        }
    )
