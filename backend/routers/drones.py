"""Drones router: fleet status and manual commands (recall)."""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.deps import get_current_user, require_admin
from backend.fleet import fleet
from backend.ws_manager import manager

router = APIRouter(prefix="/drones", tags=["drones"])


class DroneIn(BaseModel):
    name: str
    model: str = "SkyCart X1-Pro"


@router.get("")
def list_drones(user: Dict = Depends(get_current_user)):
    return {"drones": [d.to_dict() for d in fleet.drones.values()]}


@router.post("", status_code=201)
def add_drone(body: DroneIn, _: Dict = Depends(require_admin)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Drone name is required")
    drone = fleet.add_drone(body.name.strip().upper(), body.model.strip() or "SkyCart X1-Pro")
    return drone.to_dict()


@router.post("/{drone_id}/recall")
def recall_drone(drone_id: int, user: Dict = Depends(get_current_user)):
    if not fleet.recall(drone_id):
        raise HTTPException(
            status_code=400,
            detail="Drone cannot be recalled right now (not flying, or already returning)",
        )
    return {"ok": True, "drone": fleet.drones[drone_id].to_dict()}
