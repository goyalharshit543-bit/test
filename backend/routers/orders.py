"""Orders router: create, list, inspect and cancel deliveries."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.deps import get_current_user
from backend.geocode import resolve_place
from backend.order_service import cancel_order, create_order, get_order, list_orders
from backend.ws_manager import manager

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderIn(BaseModel):
    item: str = Field(min_length=2, max_length=120)
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=250)
    place: Optional[str] = Field(default=None, max_length=250,
                                 description="Place name — resolved to coordinates automatically")
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


@router.get("")
def all_orders(user: Dict = Depends(get_current_user)) -> List[Dict]:
    return list_orders(user)


@router.post("", status_code=201)
def new_order(body: OrderIn, user: Dict = Depends(get_current_user)):
    """Create an order from either a place name OR explicit lat/lng.

    If only a place name is given, it is geocoded here (the frontend also
    resolves names as you type — this covers API/SkyBot callers)."""
    lat, lng = body.lat, body.lng
    resolved_place = ""
    if lat is None or lng is None:
        if not (body.place and body.place.strip()):
            raise HTTPException(
                status_code=422,
                detail="Give a place name or click the map for coordinates",
            )
        hit = resolve_place(body.place)
        if not hit:
            raise HTTPException(status_code=422, detail=f"Place not found: {body.place}")
        lat, lng = hit["lat"], hit["lng"]
        resolved_place = hit["label"]

    order = create_order(
        user,
        item=body.item.strip(),
        customer_name=body.customer_name.strip(),
        customer_phone=body.customer_phone.strip(),
        address=body.address.strip(),
        lat=lat,
        lng=lng,
    )
    if not order.get("address"):
        # Persist the resolved/typed place name so the UI shows it everywhere.
        from backend import database as db

        label = resolved_place or (body.place or "").strip()
        if label:
            db.execute("UPDATE orders SET address = ? WHERE id = ?", (label, order["id"]))
            order["address"] = label
    return order


@router.get("/{order_id}")
def one_order(order_id: int, user: Dict = Depends(get_current_user)):
    order = get_order(user, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/{order_id}/cancel")
def cancel(order_id: int, user: Dict = Depends(get_current_user)):
    order = cancel_order(user, order_id)
    if not order:
        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled (not found, not yours, or already delivered)",
        )
    return order
