"""AI assistant router: the LangChain-powered personal AI (SkyBot)."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.ai.assistant import assistant
from backend.deps import get_current_user

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: Optional[List[Dict]] = None


@router.post("/chat")
async def chat(body: ChatIn, user: Dict = Depends(get_current_user)):
    reply, engine = await assistant.chat(user, body.message.strip(), body.history or [])
    return {"reply": reply, "engine": engine}


@router.get("/status")
def status(user: Dict = Depends(get_current_user)):
    return {"engine": assistant.engine_label()}
