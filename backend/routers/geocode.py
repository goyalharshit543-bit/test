"""Geocoding endpoints: search places by name, reverse-geocode map clicks."""
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.deps import get_current_user
from backend.geocode import resolve_place, reverse_geocode, search_places

router = APIRouter(prefix="/geocode", tags=["geocode"])


class ReverseIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.get("/search")
def geocode_search(q: str = Query(min_length=3, max_length=120),
                   user: Dict = Depends(get_current_user)) -> List[Dict]:
    """Autocomplete: 'indira nagar' → [{label, lat, lng}, …]."""
    return search_places(q)


@router.post("/reverse")
def geocode_reverse(body: ReverseIn, user: Dict = Depends(get_current_user)) -> Dict:
    """Map-click coordinates → readable place name."""
    name = reverse_geocode(body.lat, body.lng)
    if not name:
        raise HTTPException(status_code=404, detail="No place found for those coordinates")
    return {"label": name, "lat": body.lat, "lng": body.lng, "source": "reverse"}
