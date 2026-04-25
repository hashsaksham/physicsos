from html.parser import HTMLParser

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Product

router = APIRouter(prefix="/api/projects", tags=["products"])

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class _AmazonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title: str | None = None
        self.image_url: str | None = None
        self._capture_title = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        el_id = d.get("id", "")
        if el_id == "productTitle":
            self._capture_title = True
        if tag == "img" and el_id == "landingImage":
            self.image_url = d.get("src")

    def handle_data(self, data):
        if self._capture_title and data.strip():
            self.title = data.strip()
            self._capture_title = False

    def handle_endtag(self, tag):
        self._capture_title = False


class ProductRequest(BaseModel):
    amazon_url: str
    room_id: str


class ProductUpdateRequest(BaseModel):
    position_x: float | None = None
    position_y: float | None = None
    position_z: float | None = None
    rotation: float | None = None


def _product_dict(p: Product) -> dict:
    return {
        "product_id": p.id,
        "product_name": p.product_name,
        "product_image_url": p.product_image_url,
        "amazon_url": p.amazon_url,
        "position_x": p.position_x,
        "position_y": p.position_y,
        "position_z": p.position_z,
        "rotation": p.rotation,
    }


@router.post("/{project_id}/products")
async def add_product(
    project_id: str,
    body: ProductRequest,
    db: AsyncSession = Depends(get_db),
):
    parser = _AmazonParser()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(body.amazon_url, headers=_BROWSER_HEADERS)
        parser.feed(resp.text)
    except Exception:
        pass  # fall through to defaults

    product = Product(
        project_id=project_id,
        amazon_url=body.amazon_url,
        product_name=parser.title or "Unknown Product",
        product_image_url=parser.image_url,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return _product_dict(product)


@router.patch("/{project_id}/products/{product_id}")
async def update_product(
    project_id: str,
    product_id: str,
    body: ProductUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None or product.project_id != project_id:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.position_x is not None:
        product.position_x = body.position_x
    if body.position_y is not None:
        product.position_y = body.position_y
    if body.position_z is not None:
        product.position_z = body.position_z
    if body.rotation is not None:
        product.rotation = body.rotation

    await db.commit()
    await db.refresh(product)
    return _product_dict(product)


@router.get("/{project_id}/products")
async def list_products(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product).where(Product.project_id == project_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_product_dict(p) for p in rows]
