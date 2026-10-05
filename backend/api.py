import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import (
    Base,
    BlastBlock,
    BlastWindow,
    ConvergenceLog,
    SessionLocal,
    block_dict,
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
    """是否落在爆破窗内，唯一时钟来源：服务端本机 UTC 时钟。"""
    return datetime.now(timezone.utc)


def fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") + " UTC"


def parse_dt(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}不能为空")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field}时间格式不正确")
    if dt.tzinfo is None:
        # 前端正常会带时区偏移；裸时间按 UTC 兜底，绝不按客户端本机时区解释
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
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
            return jsonify({"detail": "巡检员只读，不能修改爆破窗或提交测缝"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.get("/api/clock")
def clock():
    """唯一权威时钟：页面配窗、判窗都以这里为准。"""
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

    # 客户端可上报自己的时钟，但仅作留档证据，不参与任何判定
    client_clock = body.get("client_clock")
    client_clock = str(client_clock)[:128] if client_clock is not None else None

    db = SessionLocal()
    try:
        now = server_now()
        hit = (
            db.query(BlastWindow)
            .filter(
                BlastWindow.revoked.is_(False),
                BlastWindow.chainage == chainage,
                BlastWindow.starts_at <= now,
                BlastWindow.ends_at >= now,
            )
            .order_by(BlastWindow.id)
            .with_for_update()
            .first()
        )
        if hit is not None:
            reason = (
                f"掌子面爆破封锁中：断面 {chainage} 处于爆破窗 "
                f"{fmt(hit.starts_at)} – {fmt(hit.ends_at)}，"
                f"服务端当前时刻 {fmt(now)}，测缝报送一律拒收。"
                f"请把该断面测缝作业挪到窗外时段后再提交。"
            )
            # 真实拒收与封锁日志同事务写入：日志缺失 = 这道题没完
            db.add(
                BlastBlock(
                    blocked_at=now,
                    chainage=chainage,
                    delta_mm=delta_mm,
                    submitted_by=g.user["username"],
                    window_id=hit.id,
                    window_start=hit.starts_at,
                    window_end=hit.ends_at,
                    reason=reason,
                    client_clock=client_clock,
                )
            )
            db.commit()
            return jsonify({"detail": reason, "blocked": True, "window_id": hit.id}), 409

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


@app.get("/api/blast-windows")
@require_login
def list_windows():
    db = SessionLocal()
    try:
        now = server_now()
        rows = (
            db.query(BlastWindow)
            .filter(BlastWindow.revoked.is_(False))
            .order_by(BlastWindow.id.desc())
            .all()
        )
        return jsonify([window_dict(r, now) for r in rows])
    finally:
        db.close()


@app.post("/api/blast-windows")
@require_writer
def create_window():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "断面（桩号）不能为空"}), 400
    try:
        starts_at = parse_dt(body.get("starts_at"), "起始时刻")
        ends_at = parse_dt(body.get("ends_at"), "结束时刻")
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    if ends_at <= starts_at:
        return jsonify({"detail": "结束时刻必须晚于起始时刻"}), 400

    db = SessionLocal()
    try:
        row = BlastWindow(
            chainage=chainage,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by=g.user["username"],
            created_at=server_now(),
            revoked=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(window_dict(row, server_now())), 201
    finally:
        db.close()


@app.delete("/api/blast-windows/<int:window_id>")
@require_writer
def revoke_window(window_id: int):
    db = SessionLocal()
    try:
        row = db.query(BlastWindow).filter(BlastWindow.id == window_id).with_for_update().first()
        if row is None or row.revoked:
            return jsonify({"detail": "爆破窗不存在或已解除"}), 404
        row.revoked = True
        db.commit()
        return jsonify({"ok": True, "id": window_id})
    finally:
        db.close()


@app.get("/api/blast-blocks")
@require_login
def list_blocks():
    db = SessionLocal()
    try:
        rows = db.query(BlastBlock).order_by(BlastBlock.id.desc()).all()
        return jsonify([block_dict(r) for r in rows])
    finally:
        db.close()
