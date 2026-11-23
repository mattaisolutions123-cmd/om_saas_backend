import json
from typing import List, Dict, Any
from fastapi import WebSocket


class TaskWebSocketManager:
    """
    Manages active WebSocket connections for real-time Kanban board
    and Daily Agenda task synchronization.
    """
    def __init__(self):
        # Maps branch_id -> list of active WebSockets (or "all" for global)
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, branch_id: str = "default"):
        await websocket.accept()
        if branch_id not in self.active_connections:
            self.active_connections[branch_id] = []
        self.active_connections[branch_id].append(websocket)

    def disconnect(self, websocket: WebSocket, branch_id: str = "default"):
        if branch_id in self.active_connections:
            if websocket in self.active_connections[branch_id]:
                self.active_connections[branch_id].remove(websocket)
            if not self.active_connections[branch_id]:
                del self.active_connections[branch_id]

    async def broadcast_to_branch(self, branch_id: str, message: Dict[str, Any]):
        """Broadcast payload to all connected clients in the branch and global listeners."""
        targets = set(self.active_connections.get(branch_id, []) + self.active_connections.get("all", []))
        for connection in list(targets):
            try:
                await connection.send_text(json.dumps(message, default=str))
            except Exception:
                # Stale connection clean-up
                try:
                    self.disconnect(connection, branch_id)
                except Exception:
                    pass

    async def broadcast_task_event(
        self,
        event_type: str,  # task_created, task_updated, task_moved, task_deleted, task_reassigned, sla_escalation
        task_data: Dict[str, Any],
        branch_id: str = "default",
    ):
        message = {
            "type": event_type,
            "data": task_data,
            "branch_id": branch_id,
        }
        await self.broadcast_to_branch(branch_id, message)


task_ws_manager = TaskWebSocketManager()
