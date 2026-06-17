from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BaseContext
from ..models import Product, Category
from ..templates_config import templates

router = APIRouter(tags=["shop"])


@router.get("/", name="home")
async def home(request: Request, ctx: BaseContext = Depends(BaseContext)):
    products = ctx.db.query(Product).all()
    return templates.TemplateResponse("home.html", ctx.dict(products=products))


@router.get("/detail/", name="detail")
async def detail(request: Request, id: int = 0, ctx: BaseContext = Depends(BaseContext)):
    product = ctx.db.query(Product).filter(Product.id == id).first()
    return templates.TemplateResponse("detail.html", ctx.dict(product=product))


@router.get("/category/", name="category")
async def category(request: Request, category: str = "", ctx: BaseContext = Depends(BaseContext)):
    if category:
        cat_obj = ctx.db.query(Category).filter(Category.slug == category).first()
        products = cat_obj.products if cat_obj else []
    else:
        products = ctx.db.query(Product).all()
    return templates.TemplateResponse(
        "category.html", ctx.dict(products=products, active_category=category)
    )


@router.get("/search/", name="search")
@router.post("/search/", name="search")
async def search(request: Request, ctx: BaseContext = Depends(BaseContext)):
    searched = ""
    keys = []
    if request.method == "POST":
        form = await request.form()
        searched = form.get("searched", "")
        if searched:
            keys = ctx.db.query(Product).filter(Product.name.ilike(f"%{searched}%")).all()
    return templates.TemplateResponse("search.html", ctx.dict(searched=searched, keys=keys))
