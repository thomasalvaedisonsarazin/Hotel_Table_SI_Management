import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.security import user_from_access_token
from app.database import SessionLocal
from app.models import Restaurant
from app.services.hub import hub

router = APIRouter(tags=["live"])

_AUTH_TIMEOUT_SECONDS = 10
_CLOSE_UNAUTHORIZED = 4401


def _can_watch(token: str, restaurant_id: int) -> bool:
    with SessionLocal() as db:
        user = user_from_access_token(db, token)
        restaurant = db.get(Restaurant, restaurant_id)
        return bool(user and restaurant and restaurant.owner_id == user.id)


@router.websocket("/ws/restaurants/{restaurant_id}")
async def watch_restaurant(socket: WebSocket, restaurant_id: int) -> None:
    """The token arrives as the first message, because tokens in URLs end up in server logs."""
    await socket.accept()
    try:
        message = await asyncio.wait_for(socket.receive_json(), _AUTH_TIMEOUT_SECONDS)
        token = message.get("token", "") if isinstance(message, dict) else ""
        allowed = await asyncio.to_thread(_can_watch, str(token), restaurant_id)
    except (TimeoutError, ValueError, WebSocketDisconnect):
        allowed = False
    if not allowed:
        await socket.close(code=_CLOSE_UNAUTHORIZED)
        return

    hub.join(restaurant_id, socket)
    try:
        await socket.send_json({"type": "ready"})
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(restaurant_id, socket)
