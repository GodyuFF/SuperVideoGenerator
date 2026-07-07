"""WebSocket：实时事件推送与 A2UI 确认响应接收。"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.state import state
from core.llm.a2ui.schemas import A2UIConfirmationResponse

router = APIRouter()


@router.websocket("/ws/projects/{project_id}/scripts/{script_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str, script_id: str):
    """订阅剧本频道：接收编排事件，回传 A2UI 用户确认。"""
    await websocket.accept()
    channel = state.channel_key(project_id, script_id)
    if channel not in state.ws_clients:
        state.ws_clients[channel] = []
    state.ws_clients[channel].append(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "a2ui_confirmation_response":
                # 用户通过 A2UI 模态框确认/拒绝
                response = A2UIConfirmationResponse(
                    confirmation_id=data["confirmation_id"],
                    approved=data.get("approved", False),
                    values=data.get("values", {}),
                )
                resolved = state.confirmation_manager.resolve(response)
                await websocket.send_json(
                    {
                        "type": "a2ui_confirmation_ack",
                        "resolved": resolved,
                        "confirmation_id": response.confirmation_id,
                    }
                )
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        state.ws_clients[channel].remove(websocket)
        if not state.ws_clients[channel]:
            del state.ws_clients[channel]
