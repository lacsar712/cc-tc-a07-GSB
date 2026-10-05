import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import (
    Base,
    BlastingWindow,
    BlockadeLog,
    ConvergenceLog,
    SessionLocal,
    blockade_dict,
    engine,
    row_dict,
    window_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def server_now() -> datetime:
    """唯一可信时钟：能否进爆破窗只认服务端时间，不认客户端本机时间。"""
    return datetime.now(timezone.utc)


def parse_dt(value) -> datetime | None:
    """解析 ISO-8601 时刻；不带时区的按 UTC 处理；解析失败返回 None。"""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = server_now()
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            from rules import judge

            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    delta_mm=delta,
                    status="done",
                    verdict=verdict,
                    reason=reason,
                    created_by="surveyor",
                    created_at=now,
                    processed_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "巡检员只读，不能修改"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.get("/api/time")
def server_time():
    return jsonify({"now": server_now().isoformat()})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400

    db = SessionLocal()
    try:
        # 能否进窗只看服务端时钟：此刻落在该断面任一爆破窗内，报送一律挡住。
        now = server_now()
        window = (
            db.query(BlastingWindow)
            .filter(
                BlastingWindow.chainage == chainage,
                BlastingWindow.starts_at <= now,
                BlastingWindow.ends_at >= now,
            )
            .order_by(BlastingWindow.starts_at.desc())
            .first()
        )
        if window is not None:
            reason = (
                f"断面 {chainage} 处于爆破封锁窗 "
                f"（{window.starts_at.isoformat()} 至 {window.ends_at.isoformat()}），"
                f"服务端当前时刻 {now.isoformat()} 落在窗内，测缝报送已锁死，"
                f"请把报送挪到窗外再提交。"
            )
            # 真实拒收必须落痕：写封锁日志，且不创建任何测缝记录。
            db.add(
                BlockadeLog(
                    window_id=window.id,
                    chainage=chainage,
                    delta_mm=delta_mm,
                    blocked_by=g.user["username"],
                    server_time=now,
                    reason=reason,
                )
            )
            db.commit()
            return jsonify({"detail": reason, "window_id": window.id}), 423

        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status="pending",
            created_by=g.user["username"],
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()


@app.get("/api/blasting-windows")
@require_login
def list_windows():
    db = SessionLocal()
    try:
        rows = db.query(BlastingWindow).order_by(BlastingWindow.starts_at.desc()).all()
        return jsonify([window_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/blasting-windows")
@require_writer
def create_window():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "断面不能为空"}), 400
    starts_at = parse_dt(body.get("starts_at"))
    ends_at = parse_dt(body.get("ends_at"))
    if starts_at is None or ends_at is None:
        return jsonify({"detail": "起止时刻格式不正确"}), 400
    if ends_at <= starts_at:
        return jsonify({"detail": "结束时刻必须晚于开始时刻"}), 400

    db = SessionLocal()
    try:
        row = BlastingWindow(
            chainage=chainage,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by=g.user["username"],
            created_at=server_now(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(window_dict(row)), 201
    finally:
        db.close()


@app.delete("/api/blasting-windows/<int:window_id>")
@require_writer
def delete_window(window_id: int):
    db = SessionLocal()
    try:
        row = db.get(BlastingWindow, window_id)
        if row is None:
            return jsonify({"detail": "爆破窗不存在"}), 404
        db.delete(row)
        db.commit()
        return jsonify({"deleted": window_id})
    finally:
        db.close()


@app.get("/api/blockade-logs")
@require_login
def list_blockade_logs():
    db = SessionLocal()
    try:
        rows = db.query(BlockadeLog).order_by(BlockadeLog.id.desc()).all()
        return jsonify([blockade_dict(r) for r in rows])
    finally:
        db.close()
