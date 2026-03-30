"""
Notifications router.
- GET  /notifications/         → paginated list for current user
- PUT  /notifications/{id}/read → mark one read
- PUT  /notifications/read-all  → mark all read
- WS   /notifications/ws/{token} → real-time push channel

Notifications are derived from:
  • Unread messages received
  • Recent activity events (enrollments, certs, live classes, etc.)
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Dict, List, Optional
from datetime import datetime, timezone
from app.database import get_db
from app.models import Message, Employee, Enrollment, Certificate, LiveClass, Course
from app.dependencies import require_employee
from app.auth import decode_token

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ─── WebSocket connection manager (shared push channel) ───────────────────────

class NotifConnectionManager:
    def __init__(self):
        self.connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: int, ws: WebSocket):
        if user_id in self.connections:
            try:
                self.connections[user_id].remove(ws)
            except ValueError:
                pass

    async def push(self, user_id: int, payload: dict):
        """Push a single notification to all open tabs of a user."""
        for ws in list(self.connections.get(user_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                pass


notif_manager = NotifConnectionManager()


# ─── Expose manager so messages router can push "new message" notifs ──────────
def get_notif_manager():
    return notif_manager


# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws")
async def notif_ws(websocket: WebSocket, token: Optional[str] = Query(None)):
    payload = decode_token(token) if token else None
    if not payload:
        await websocket.close(code=1008)
        return
    user_id: int = payload.get("id")
    if not user_id:
        await websocket.close(code=1008)
        return

    await notif_manager.connect(user_id, websocket)
    try:
        while True:
            # Keep connection alive; client sends pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        notif_manager.disconnect(user_id, websocket)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _time_ago(dt: datetime) -> str:
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 60:
        return "Just now"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


# ─── GET /notifications/ ──────────────────────────────────────────────────────

@router.get("/")
@router.get("")
def get_notifications(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    notifs = []

    # 1. Unread messages
    unread_msgs = (
        db.query(Message)
        .options(joinedload(Message.sender))
        .filter(Message.receiver_id == current.id, Message.is_read == False)
        .order_by(Message.sent_at.desc())
        .limit(20)
        .all()
    )
    for m in unread_msgs:
        sender_name = m.sender.name if m.sender else "Someone"
        notifs.append({
            "id": f"msg-{m.id}",
            "type": "message",
            "userId": m.sender_id,
            "icon": "💬",
            "message": f"New message from {sender_name}",
            "time": _time_ago(m.sent_at),
            "ts": m.sent_at.timestamp() if m.sent_at else 0,
            "read": False
        })

    # 2. Recent enrollments (for admins / managers)
    if current.role.value in ("super_admin", "hr_admin", "manager"):
        enrollments = (
            db.query(Enrollment, Employee, Course)
            .join(Employee, Enrollment.employee_id == Employee.id)
            .join(Course, Enrollment.course_id == Course.id)
            .order_by(Enrollment.enrolled_at.desc())
            .limit(10)
            .all()
        )
        for enr, emp, course in enrollments:
            notifs.append({
                "id": f"enr-{enr.id}",
                "type": "enrollment",
                "icon": "📚",
                "message": f"{emp.name} enrolled in {course.title}",
                "time": _time_ago(enr.enrolled_at),
                "ts": enr.enrolled_at.timestamp() if enr.enrolled_at else 0,
                "read": True
            })

    # 3. Certificates earned by current user
    from app.models import Certificate
    certs = (
        db.query(Certificate, Course)
        .join(Course, Certificate.course_id == Course.id)
        .filter(Certificate.employee_id == current.id)
        .order_by(Certificate.issued_at.desc())
        .limit(5)
        .all()
    )
    for cert, course in certs:
        notifs.append({
            "id": f"cert-{cert.id}",
            "type": "certificate",
            "icon": "🏆",
            "message": f"You earned a certificate for {course.title}",
            "time": _time_ago(cert.issued_at),
            "ts": cert.issued_at.timestamp() if cert.issued_at else 0,
            "read": True
        })

    # 4. Upcoming live classes accessible to this user
    upcoming = (
        db.query(LiveClass)
        .filter(LiveClass.status == "upcoming")
        .order_by(LiveClass.created_at.desc())
        .limit(5)
        .all()
    )
    for lc in upcoming:
        notifs.append({
            "id": f"lc-{lc.id}",
            "type": "live_class",
            "icon": "🎥",
            "message": f"Upcoming live class: {lc.title} on {lc.date} at {lc.time}",
            "time": _time_ago(lc.created_at),
            "ts": lc.created_at.timestamp() if lc.created_at else 0,
            "read": True
        })

    # Sort newest first
    notifs.sort(key=lambda x: x["ts"], reverse=True)
    return notifs[:30]
