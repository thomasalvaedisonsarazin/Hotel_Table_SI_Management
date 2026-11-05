import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.access import role_for
from app.auth.security import user_from_access_token
from app.database import SessionLocal
from app.models import Restaurant
from app.services.hub import hub

router = APIRouter(tags=["live"])

_AUTH_TIMEOUT_SECONDS = 10
_CLOSE_UNAUTHORIZED = 4401


def _watcher_id(token: str, restaurant_id: int) -> int | None:
    with SessionLocal() as db:
        user = user_from_access_token(db, token)
        restaurant = db.get(Restaurant, restaurant_id)
        if user is None or restaurant is None or user.must_change_password:
            return None
        return user.id if role_for(db, restaurant, user) else None


@router.websocket("/ws/restaurants/{restaurant_id}")
async def watch_restaurant(socket: WebSocket, restaurant_id: int) -> None:
    """The token arrives as the first message, because tokens in URLs end up in server logs."""
    await socket.accept()
    try:
        message = await asyncio.wait_for(socket.receive_json(), _AUTH_TIMEOUT_SECONDS)
        token = message.get("token", "") if isinstance(message, dict) else ""
        user_id = await asyncio.to_thread(_watcher_id, str(token), restaurant_id)
    except (TimeoutError, ValueError, WebSocketDisconnect):
        user_id = None
    if user_id is None:
        await socket.close(code=_CLOSE_UNAUTHORIZED)
        return

    socket.state.user_id = user_id
    hub.join(restaurant_id, socket)
    try:
        await socket.send_json({"type": "ready"})
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(restaurant_id, socket)
