from fastapi import APIRouter, Request, Depends
from ..dependencies import BaseContext
from ..templates_config import templates

router = APIRouter(tags=["pages"])


@router.get("/about/", name="about")
async def about(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse("about.html", ctx.dict())


@router.get("/contact/", name="contact")
async def contact(request: Request, ctx: BaseContext = Depends(BaseContext)):
    return templates.TemplateResponse("contact.html", ctx.dict())
