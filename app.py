import csv
import io
import os
import secrets
import sqlite3
import uuid
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import qrcode
import psycopg
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, abort, flash, g, make_response, redirect, render_template_string, request, send_file, session, url_for
from psycopg.rows import dict_row
from supabase import create_client
from werkzeug.utils import safe_join, secure_filename
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("LAB_DATABASE", BASE_DIR / "instance" / "lab.sqlite3"))
UPLOADS_DIR = Path(os.environ.get("LAB_UPLOADS", BASE_DIR / "instance" / "uploads"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "lab-files").strip()
_supabase_client = None
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}
CATEGORY_CHOICES = (
    "Máy tính",
    "KIT thực hành",
    "Board mạch & module",
    "Linh kiện điện tử",
    "Thiết bị đo",
    "Dụng cụ & phụ kiện",
    "Khác",
)

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','staff','lecturer','student')),
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Khác',
    location TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 0),
    minimum_stock INTEGER NOT NULL DEFAULT 0 CHECK(minimum_stock >= 0),
    unit_price INTEGER CHECK(unit_price IS NULL OR unit_price >= 0),
    notes TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    borrower_id INTEGER NOT NULL REFERENCES users(id),
    borrower_name TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    purpose TEXT NOT NULL,
    borrowed_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    issued_by INTEGER NOT NULL REFERENCES users(id),
    giver_signature TEXT NOT NULL,
    receiver_signature TEXT NOT NULL,
    returned_at TEXT,
    received_by INTEGER REFERENCES users(id),
    return_signature TEXT NOT NULL DEFAULT ''
);
"""

POSTGRES_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','staff','lecturer','student')),
        active BOOLEAN NOT NULL DEFAULT TRUE
    )""",
    """CREATE TABLE IF NOT EXISTS items (
        id BIGSERIAL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Khác',
        location TEXT NOT NULL DEFAULT '',
        quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 0),
        minimum_stock INTEGER NOT NULL DEFAULT 0 CHECK(minimum_stock >= 0),
        unit_price BIGINT CHECK(unit_price IS NULL OR unit_price >= 0),
        notes TEXT NOT NULL DEFAULT '',
        image_path TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS loans (
        id BIGSERIAL PRIMARY KEY,
        item_id BIGINT NOT NULL REFERENCES items(id),
        borrower_id BIGINT NOT NULL REFERENCES users(id),
        borrower_name TEXT NOT NULL DEFAULT '',
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        purpose TEXT NOT NULL,
        borrowed_at TEXT NOT NULL,
        due_at TEXT NOT NULL,
        issued_by BIGINT NOT NULL REFERENCES users(id),
        giver_signature TEXT NOT NULL,
        receiver_signature TEXT NOT NULL,
        returned_at TEXT,
        received_by BIGINT REFERENCES users(id),
        return_signature TEXT NOT NULL DEFAULT ''
    )""",
)

PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · Lab</title>
<style>
:root{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#37352f;background:#fff;font-synthesis:none;text-rendering:optimizeLegibility}*{box-sizing:border-box}body{margin:0}.sidebar{position:fixed;inset:0 auto 0 0;width:238px;padding:20px 12px;background:#f7f7f5;border-right:1px solid #eee;display:flex;flex-direction:column;z-index:2}.workspace{display:flex;align-items:center;gap:10px;padding:5px 10px 22px;font-weight:650;color:#292823;text-decoration:none}.logo{width:30px;height:30px;border-radius:8px;background:#e8e6df;display:grid;place-items:center}.side-label{font-size:11px;text-transform:uppercase;color:#9b9991;letter-spacing:.07em;margin:8px 10px}.nav{display:flex;gap:10px;align-items:center;color:#62615d;text-decoration:none;padding:8px 10px;border-radius:6px;font-size:14px}.nav:hover,.nav.active{background:#ecebe8;color:#25241f}.nav-icon{width:18px;text-align:center;color:#85837b}.side-bottom{margin-top:auto;padding:10px;font-size:12px;color:#8b8981}.topbar{height:48px;position:fixed;z-index:1;left:238px;right:0;top:0;background:#ffffffed;border-bottom:1px solid #efefed;display:flex;align-items:center;justify-content:space-between;padding:0 34px;color:#828078;font-size:13px}.topbar a{color:#66645d;text-decoration:none}.topbar a:hover{color:#111}.main{margin-left:238px;padding:84px 42px 70px;max-width:1460px}.page-head{margin:0 0 28px}.eyebrow{font-size:13px;color:#89877f;margin-bottom:9px}.page-head h1{font-size:32px;letter-spacing:-.035em;font-weight:650;margin:0 0 7px}.subtitle{color:#8b8981;font-size:14px}.section{margin:34px 0 0;scroll-margin-top:72px}.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px}.section-title h2{font-size:17px;font-weight:620;margin:0}.muted{color:#8b8981}.small{font-size:12px}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0 30px}.stat{border:1px solid #eae9e6;border-radius:8px;padding:16px 18px;background:#fff}.stat-label{font-size:12px;color:#8c8981}.metric{font-size:26px;font-weight:650;margin-top:5px;letter-spacing:-.03em}.metric.currency{font-size:20px}.notice{border:1px solid #f0dfb8;background:#fffaf0;border-radius:7px;padding:12px 14px;margin:8px 0;font-size:13px}.notice.danger{border-color:#f0c7c2;background:#fff7f5}.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:13px}.item-card,.loan-card,.panel{border:1px solid #e9e8e5;border-radius:8px;background:#fff;overflow:hidden}.item-photo{height:150px;background:#f4f4f1;display:grid;place-items:center;color:#b2b0a8;font-size:30px;overflow:hidden}.item-photo img{width:100%;height:100%;object-fit:cover}.item-content{padding:13px 14px}.item-code{font-size:11px;color:#a09e96;letter-spacing:.025em}.item-name{font-size:15px;font-weight:600;margin:5px 0 4px}.item-meta{font-size:12px;color:#89877f}.asset-price{font-size:13px;font-weight:600;margin-top:8px;color:#35332e}.category-nav{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 19px}.category-nav a{border:1px solid #e7e5e1;background:#fbfbfa;border-radius:999px;padding:7px 10px;color:#5f5d56;text-decoration:none;font-size:12px}.category-nav a:hover{border-color:#c9c7c0;background:#f2f1ee}.inventory-group{margin:28px 0}.inventory-group:first-of-type{margin-top:0}.group-title{display:flex;align-items:baseline;gap:8px;margin:0 0 11px;font-size:15px}.group-title span{font-size:12px;color:#8b8981;font-weight:400}.item-actions{display:flex;gap:13px;margin-top:12px;font-size:12px}.item-actions a,.text-link{color:#69675f;text-decoration:none}.item-actions a:hover,.text-link:hover{text-decoration:underline}.pill{display:inline-block;background:#f1f0ed;border-radius:4px;padding:3px 6px;font-size:11px;color:#6c6a62}.pill.warn{background:#fff1d6;color:#8b5d08}.loan-list{display:grid;gap:10px}.loan-card{padding:14px 16px;display:flex;justify-content:space-between;gap:20px;align-items:center}.loan-main{min-width:0}.loan-name{font-weight:600;font-size:14px}.loan-detail{color:#817f77;font-size:12px;margin-top:5px;line-height:1.55}.loan-actions{display:flex;align-items:center;gap:10px;flex-shrink:0}.button,button{display:inline-flex;align-items:center;justify-content:center;border:1px solid #e5e4e0;background:#fff;color:#44423d;padding:7px 11px;border-radius:6px;text-decoration:none;font:inherit;font-size:13px;cursor:pointer}.button:hover,button:hover{background:#f7f7f5}.button.primary,button.primary{background:#37352f;color:#fff;border-color:#37352f}.button.primary:hover,button.primary:hover{background:#55534c}.button.small-btn{padding:5px 8px;font-size:12px}.panel{padding:17px 18px;margin-top:13px}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 14px}label{display:block;font-size:12px;color:#74726a;margin:10px 0 5px}input,select,textarea{width:100%;border:1px solid #e4e3df;border-radius:6px;padding:9px 10px;font:inherit;font-size:13px;color:#37352f;background:#fff}input:focus,select:focus,textarea:focus{outline:2px solid #d8e5d8;border-color:#9caf99}textarea{min-height:74px;resize:vertical}.form-actions{margin-top:12px}.file-note{font-size:11px;color:#929087;margin-top:3px}.flash{border:1px solid #d6e8d5;background:#f2faf1;border-radius:6px;padding:10px 13px;margin:0 0 14px;font-size:13px}.empty{border:1px dashed #e4e3df;border-radius:8px;padding:25px;text-align:center;color:#96948b;font-size:13px}.loan-time{font-variant-numeric:tabular-nums}.slip{max-width:820px;margin:0 auto;border:1px solid #e7e6e2;padding:36px;border-radius:8px}.slip h1{font-size:25px}.slip-row{display:grid;grid-template-columns:170px 1fr;border-bottom:1px solid #efeeeb;padding:11px 0;font-size:14px}.signatures{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:42px}.signature{border-top:1px solid #c9c7bf;padding-top:10px;text-align:center;min-height:90px;font-size:12px;color:#77756d}.slip-tools{display:flex;justify-content:space-between;margin-bottom:16px}.admin-tools{border-left:2px solid #e8e6df;padding-left:12px;margin-bottom:14px}.hide{display:none}@media(max-width:800px){.sidebar{position:static;width:auto;height:auto;padding:10px;display:flex;flex-direction:row;align-items:center;overflow:auto;border-right:0;border-bottom:1px solid #eee}.workspace{padding:4px 8px 4px 2px;white-space:nowrap}.side-label,.side-bottom{display:none}.nav{white-space:nowrap;padding:7px 8px}.topbar{position:static;height:40px;padding:0 15px}.main{margin-left:0;padding:24px 16px 45px}.page-head h1{font-size:27px}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.stat{padding:12px}.metric{font-size:22px}.loan-card{align-items:flex-start;flex-direction:column;gap:12px}.loan-actions{width:100%;justify-content:flex-start}.slip{padding:22px 16px}}@media(max-width:520px){.form-grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.stat:last-child{grid-column:span 2}.card-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.item-photo{height:115px}.item-content{padding:10px}.item-name{font-size:13px}.slip-row{grid-template-columns:110px 1fr}.signatures{gap:14px}}
@media print{.sidebar,.topbar,.slip-tools{display:none!important}.main{margin:0;padding:0;max-width:none}.slip{border:0;padding:0;max-width:none}}
.item-photo{position:relative}.item-photo:has(img)::after{content:'© Lê Bá Đăng Hoàng';position:absolute;right:7px;bottom:7px;background:#25241fcc;color:#fff;padding:4px 7px;border-radius:4px;font-size:10px;pointer-events:none}.protected-media,.protected-copy,.signature{user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}.protected-media img{pointer-events:none;-webkit-user-drag:none;user-drag:none}.slip{position:relative;isolation:isolate}.slip::after{content:'ĐIỆN TỬ SỐ';position:absolute;z-index:-1;top:48%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);white-space:nowrap;font-size:clamp(20px,5vw,42px);font-weight:700;letter-spacing:.08em;color:#37352f;opacity:.09;pointer-events:none}.author-footer{margin:0 0 24px 280px;padding:12px 42px;color:#96948b;font-size:12px}@media(max-width:800px){.author-footer{margin:0;padding:12px 16px}}
</style></head><body>
<aside class="sidebar"><a class="workspace" href="{{ url_for('index') }}"><span class="logo">⚡</span><span>Điện tử số Lab</span></a><div class="side-label">Không gian làm việc</div>
<a class="nav active" href="{{ url_for('index') }}"><span class="nav-icon">⌂</span>Tổng quan</a><a class="nav" href="{{ url_for('index') }}#inventory"><span class="nav-icon">▦</span>Kho thiết bị</a><a class="nav" href="{{ url_for('index') }}#loans"><span class="nav-icon">▤</span>Phiếu mượn</a>{% if user and user.role == 'admin' %}<a class="nav" href="{{ url_for('reports') }}"><span class="nav-icon">↧</span>Báo cáo CSV</a>{% endif %}
<div class="side-bottom">Phòng thí nghiệm Điện tử số<br>Trang xem công khai</div></aside>
<div class="topbar"><span>Điện tử số Lab <span class="muted">/</span> {{ title }}</span>{% if user %}<span>{{ user.full_name }} · <a href="{{ url_for('logout') }}">Đăng xuất</a></span>{% else %}<a href="{{ url_for('login') }}">Admin</a>{% endif %}</div>
<main class="main">{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}{{ body|safe }}</main><footer class="author-footer">Tác giả: Lê Bá Đăng Hoàng</footer><script>document.addEventListener('contextmenu',function(event){if(event.target.closest('.protected-media,.protected-copy,.signature'))event.preventDefault()});document.addEventListener('dragstart',function(event){if(event.target.closest('.protected-media,.protected-copy,.signature'))event.preventDefault()});document.addEventListener('copy',function(event){const selection=window.getSelection();if(selection&&selection.anchorNode){const node=selection.anchorNode.nodeType===Node.ELEMENT_NODE?selection.anchorNode:selection.anchorNode.parentElement;if(node&&node.closest('.protected-copy,.signature'))event.preventDefault()}})</script></body></html>"""

def connect_db():
    if DATABASE_URL:
        return PostgresConnection(DATABASE_URL)
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exception_type, exception, traceback):
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self.close()


class PostgresConnection:
    def __init__(self, connection_url):
        self.connection = psycopg.connect(connection_url, row_factory=dict_row)

    def execute(self, statement, parameters=()):
        cursor = self.connection.cursor()
        cursor.execute(statement.replace("?", "%s"), parameters)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, exception_type, _exception, _traceback):
        try:
            if exception_type:
                self.connection.rollback()
            else:
                self.connection.commit()
        finally:
            self.connection.close()


class StorageError(Exception):
    pass


def supabase_storage_enabled():
    return bool(SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)


def get_supabase_client():
    global _supabase_client
    if not supabase_storage_enabled():
        return None
    if not all((SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET)):
        raise StorageError("Thiếu cấu hình Supabase Storage.")
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_client


def save_image(filename, upload, content_type):
    upload.stream.seek(0)
    if supabase_storage_enabled():
        try:
            get_supabase_client().storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                path=f"uploads/{filename}",
                file=upload.stream.read(),
                file_options={"content-type": content_type, "cache-control": "private, max-age=0", "upsert": "false"},
            )
        except Exception as error:
            raise StorageError("Không thể lưu ảnh vào Supabase Storage.") from error
        return
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    upload.save(UPLOADS_DIR / filename)


def delete_image(filename):
    if not filename:
        return
    if supabase_storage_enabled():
        try:
            get_supabase_client().storage.from_(SUPABASE_STORAGE_BUCKET).remove([f"uploads/{filename}"])
        except Exception as error:
            raise StorageError("Không thể xóa ảnh trên Supabase Storage.") from error
        return
    (UPLOADS_DIR / filename).unlink(missing_ok=True)


def get_image_stream(filename):
    if supabase_storage_enabled():
        try:
            return io.BytesIO(get_supabase_client().storage.from_(SUPABASE_STORAGE_BUCKET).download(f"uploads/{filename}"))
        except Exception as error:
            raise StorageError("Không thể đọc ảnh từ Supabase Storage.") from error
    image_path = safe_join(str(UPLOADS_DIR), filename)
    if not image_path or not Path(image_path).is_file():
        raise FileNotFoundError
    return open(image_path, "rb")


def init_db():
    with connect_db() as db:
        if DATABASE_URL:
            for statement in POSTGRES_SCHEMA:
                db.execute(statement)
            db.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS image_path TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS unit_price BIGINT")
            db.execute("ALTER TABLE loans ADD COLUMN IF NOT EXISTS borrower_name TEXT NOT NULL DEFAULT ''")
        else:
            db.executescript(SQLITE_SCHEMA)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(items)")}
            if "image_path" not in columns:
                db.execute("ALTER TABLE items ADD COLUMN image_path TEXT NOT NULL DEFAULT ''")
            if "unit_price" not in columns:
                db.execute("ALTER TABLE items ADD COLUMN unit_price INTEGER")
            loan_columns = {row["name"] for row in db.execute("PRAGMA table_info(loans)")}
            if "borrower_name" not in loan_columns:
                db.execute("ALTER TABLE loans ADD COLUMN borrower_name TEXT NOT NULL DEFAULT ''")
        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")
        if username and password and not db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            db.execute("INSERT INTO users(username, full_name, password_hash, role) VALUES(?,?,?, 'admin')",
                       (username, "Quản trị viên", generate_password_hash(password)))


def current_user():
    if "user" not in g:
        user_id = session.get("user_id")
        g.user = None
        if user_id:
            with connect_db() as db:
                g.user = db.execute("SELECT * FROM users WHERE id = ? AND active", (user_id,)).fetchone()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user()["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


@app.before_request
def csrf_guard():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
            abort(400, "Phiên gửi biểu mẫu không hợp lệ. Vui lòng tải lại trang.")


@app.context_processor
def shared_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "user": current_user(),
        "csrf_token": session["csrf_token"],
        "format_vnd": format_vnd,
    }


def format_vnd(value):
    if value is None:
        return "Chưa cập nhật"
    return f"{value:,}".replace(",", ".") + " ₫"


def parse_vnd(value):
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    for marker in ("vnd", "đ", "₫", ".", ",", " "):
        cleaned = cleaned.replace(marker, "")
    if not cleaned.isdigit():
        raise ValueError
    amount = int(cleaned)
    if amount > 1_000_000_000_000:
        raise ValueError
    return amount


def page(title, body, **context):
    html = render_template_string(body, **context)
    return render_template_string(PAGE, title=title, body=html)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ? AND active", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("index"))
        flash("Tên đăng nhập hoặc mật khẩu không đúng.")
    body = """<div class="page-head"><div class="eyebrow">Khu vực quản trị</div><h1>Đăng nhập admin</h1><div class="subtitle">Khách có thể xem kho và phiếu mượn mà không cần tài khoản.</div></div><section class="panel" style="max-width:440px"><form method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><label>Tên đăng nhập</label><input name="username" required autofocus><label>Mật khẩu</label><input type="password" name="password" required><div class="form-actions"><button class="primary">Đăng nhập</button></div></form><p class="muted small">Tài khoản admin được khởi tạo bằng ADMIN_USERNAME và ADMIN_PASSWORD.</p></section>"""
    return page("Đăng nhập", body)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/")
def index():
    with connect_db() as db:
        items = db.execute("SELECT * FROM items ORDER BY LOWER(name)").fetchall()
        loans = db.execute("""SELECT l.*, i.code, i.name AS item_name,
            COALESCE(NULLIF(l.borrower_name,''),u.full_name) AS actual_borrower,
            issuer.full_name AS issuer_name, receiver.full_name AS receiver_name
            FROM loans l JOIN items i ON i.id=l.item_id JOIN users u ON u.id=l.borrower_id
            JOIN users issuer ON issuer.id=l.issued_by LEFT JOIN users receiver ON receiver.id=l.received_by
            ORDER BY CASE WHEN l.returned_at IS NULL THEN 0 ELSE 1 END, l.borrowed_at DESC LIMIT 100""").fetchall()
    active_loans = [loan for loan in loans if not loan["returned_at"]]
    low = [item for item in items if item["quantity"] <= item["minimum_stock"]]
    today_date = date.today()
    overdue_loans = [
        {"loan": loan, "days_overdue": (today_date - date.fromisoformat(loan["due_at"])).days}
        for loan in active_loans if loan["due_at"] < today_date.isoformat()
    ]
    grouped_items = {category: [] for category in CATEGORY_CHOICES}
    custom_groups = {}
    for item in items:
        category = item["category"] or "Khác"
        if category in grouped_items:
            grouped_items[category].append(item)
        else:
            custom_groups.setdefault(category, []).append(item)
    inventory_groups = [
        {"name": category, "anchor": f"category-{index}", "items": grouped_items[category]}
        for index, category in enumerate(CATEGORY_CHOICES, start=1) if grouped_items[category]
    ]
    for category, group_items in sorted(custom_groups.items()):
        inventory_groups.append({"name": category, "anchor": f"category-{len(inventory_groups) + 1}", "items": group_items})
    inventory_value = sum(item["quantity"] * (item["unit_price"] or 0) for item in items)
    body = """<div class="page-head"><div class="eyebrow">Không gian làm việc / Tổng quan</div><h1>Phòng thí nghiệm Điện tử số</h1><div class="subtitle">Theo dõi tài sản, vật tư và các phiếu bàn giao của phòng thí nghiệm.</div></div>
    <div class="stats"><div class="stat"><div class="stat-label">Mặt hàng trong kho</div><div class="metric">{{ items|length }}</div></div><div class="stat"><div class="stat-label">Phiếu đang mượn</div><div class="metric">{{ active_loans|length }}</div></div><div class="stat"><div class="stat-label">Cảnh báo tồn thấp</div><div class="metric">{{ low|length }}</div></div><div class="stat"><div class="stat-label">Giá trị tồn kho</div><div class="metric currency">{{ format_vnd(inventory_value) }}</div></div></div>
    {% if overdue_loans %}<section class="section"><div class="section-title"><h2>⚠ Cảnh báo mượn quá lâu</h2><span class="muted small">{{ overdue_loans|length }} phiếu cần xử lý</span></div>{% for alert in overdue_loans %}<div class="notice danger"><strong>{{ alert.loan.code }} · {{ alert.loan.item_name }}</strong> — {{ alert.loan.actual_borrower }} đang mượn quá hạn <strong>{{ alert.days_overdue }} ngày</strong> (hạn trả {{ alert.loan.due_at }}).</div>{% endfor %}</section>{% endif %}
    {% if low %}<section class="section"><div class="section-title"><h2>⚠ Cần bổ sung</h2></div>{% for item in low %}<div class="notice"><strong>{{ item.code }}</strong> · {{ item.name }} — còn {{ item.quantity }}, mức tối thiểu {{ item.minimum_stock }}</div>{% endfor %}</section>{% endif %}
    <section class="section" id="inventory"><div class="section-title"><h2>▦ Kho thiết bị</h2><span class="muted small">{{ items|length }} mặt hàng · phân theo nhóm tài sản</span></div>
    {% if user and user.role == 'admin' %}<details class="panel"><summary style="cursor:pointer;font-size:13px;font-weight:600">＋ Thêm mặt hàng hoặc cập nhật số liệu</summary><form method="post" enctype="multipart/form-data" action="{{ url_for('add_item') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><div class="form-grid"><div><label>Mã thiết bị</label><input name="code" required></div><div><label>Tên mặt hàng</label><input name="name" required></div><div><label>Nhóm tài sản</label><select name="category">{% for category in category_choices %}<option value="{{ category }}">{{ category }}</option>{% endfor %}</select></div><div><label>Vị trí lưu kho</label><input name="location"></div><div><label>Số lượng hiện có</label><input type="number" min="0" name="quantity" value="1" required></div><div><label>Mức tồn tối thiểu</label><input type="number" min="0" name="minimum_stock" value="0"></div><div><label>Giá đơn vị (VNĐ, tùy chọn)</label><input name="unit_price" inputmode="numeric" placeholder="Ví dụ: 1500000"><div class="file-note">Bỏ trống nếu chưa cập nhật giá tài sản.</div></div><div><label>Hình ảnh thiết bị</label><input type="file" name="image" accept="image/png,image/jpeg,image/webp,image/gif"><div class="file-note">PNG, JPG, WEBP hoặc GIF · tối đa 4 MB</div></div></div><label>Ghi chú</label><textarea name="notes"></textarea><div class="form-actions"><button class="primary">Lưu mặt hàng</button></div></form></details>{% endif %}
    {% if inventory_groups %}<nav class="category-nav" aria-label="Nhóm tài sản">{% for group in inventory_groups %}<a href="#{{ group['anchor'] }}">{{ group['name'] }} · {{ group['items']|length }}</a>{% endfor %}</nav>{% for group in inventory_groups %}<section class="inventory-group" id="{{ group['anchor'] }}"><h3 class="group-title">{{ group['name'] }} <span>{{ group['items']|length }} mặt hàng</span></h3><div class="card-grid">{% for item in group['items'] %}<article class="item-card"><div class="item-photo protected-media">{% if item.image_path %}<img draggable="false" src="{{ url_for('uploaded_image', filename=item.image_path) }}" alt="Ảnh {{ item.name }}">{% else %}<span>▧</span>{% endif %}</div><div class="item-content"><div class="item-code">{{ item.code }}</div><div class="item-name">{{ item.name }}</div><div class="item-meta">{{ item.location or 'Chưa cập nhật vị trí' }}</div><div class="asset-price">{% if item.unit_price is not none %}{{ format_vnd(item.unit_price) }} / đơn vị{% else %}Chưa cập nhật giá{% endif %}</div><div style="margin-top:9px"><span class="pill">Còn {{ item.quantity }}</span> {% if item.quantity <= item.minimum_stock %}<span class="pill warn">Tồn thấp</span>{% endif %}</div><div class="item-actions"><a href="{{ url_for('item_qr', item_id=item.id) }}">Mã QR ↗</a></div></div></article>{% endfor %}</div></section>{% endfor %}{% else %}<div class="empty">Chưa có mặt hàng trong kho. Admin có thể thêm máy tính, KIT thực hành, linh kiện hoặc thiết bị đo ở trên.</div>{% endif %}</section>
    <section class="section" id="loans"><div class="section-title"><h2>▤ Phiếu mượn và bàn giao</h2><span class="muted small">{{ loans|length }} phiếu gần đây</span></div>
    {% if user and user.role == 'admin' %}<details class="panel"><summary style="cursor:pointer;font-size:13px;font-weight:600">＋ Lập phiếu mượn</summary><form method="post" action="{{ url_for('add_loan') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><div class="form-grid"><div><label>Thiết bị</label><select name="item_id" required>{% for item in items if item.quantity > 0 %}<option value="{{ item.id }}">{{ item.code }} — {{ item.name }} ({{ item.quantity }})</option>{% endfor %}</select></div><div><label>Họ tên người mượn</label><input name="borrower_name" required></div><div><label>Số lượng</label><input type="number" name="quantity" min="1" value="1" required></div><div><label>Hạn trả</label><input type="date" name="due_at" min="{{ today }}" required></div><div><label>Người giao ký tên</label><input name="giver_signature" required></div><div><label>Người nhận ký tên</label><input name="receiver_signature" required></div></div><label>Mục đích sử dụng</label><textarea name="purpose" required></textarea><div class="form-actions"><button class="primary">Tạo phiếu mượn</button></div></form></details>{% endif %}
    <div class="loan-list">{% for loan in loans %}<article class="loan-card"><div class="loan-main"><div class="loan-name">{{ loan.code }} · {{ loan.item_name }} <span class="pill">#{{ loan.id }}</span></div><div class="loan-detail">Người mượn: {{ loan.actual_borrower }} · SL {{ loan.quantity }} · Hạn trả {{ loan.due_at }}<br>{{ loan.purpose }} · <span class="loan-time" data-borrowed="{{ loan.borrowed_at }}">Đang tính thời gian</span>{% if loan.due_at < today and not loan.returned_at %} · <span style="color:#9b6500">Quá hạn</span>{% endif %}</div></div><div class="loan-actions">{% if loan.returned_at %}<span class="pill">Đã trả</span>{% else %}<span class="pill warn">Đang mượn</span>{% endif %}<a class="button small-btn" href="{{ url_for('loan_slip', loan_id=loan.id) }}">Mở phiếu</a>{% if user and user.role == 'admin' and not loan.returned_at %}<form method="post" action="{{ url_for('return_loan', loan_id=loan.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input name="return_signature" placeholder="Người nhận trả ký tên" required><button class="small-btn">Ghi nhận trả</button></form>{% endif %}</div></article>{% else %}<div class="empty">Chưa có phiếu mượn.</div>{% endfor %}</div></section>
    <script>document.querySelectorAll('.loan-time').forEach(function(el){const start=new Date(el.dataset.borrowed.replace(' ','T')+'Z');function tick(){let s=Math.max(0,Math.floor((Date.now()-start.getTime())/1000)),d=Math.floor(s/86400);s%=86400;let h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);el.textContent='Đã mượn '+d+' ngày '+h+' giờ '+m+' phút'}tick();setInterval(tick,60000)})</script>"""
    return page("Tổng quan", body, items=items, loans=loans, active_loans=active_loans, low=low,
                overdue_loans=overdue_loans, inventory_groups=inventory_groups, inventory_value=inventory_value,
                category_choices=CATEGORY_CHOICES, today=today_date.isoformat())


@app.post("/items")
@roles_required("admin")
def add_item():
    code, name = request.form.get("code", "").strip(), request.form.get("name", "").strip()
    image_path = ""
    try:
        quantity = int(request.form.get("quantity", "1"))
        minimum = int(request.form.get("minimum_stock", "0"))
        unit_price = parse_vnd(request.form.get("unit_price"))
        category = request.form.get("category", "Khác").strip() or "Khác"
        if not code or not name or category not in CATEGORY_CHOICES or quantity < 0 or minimum < 0:
            raise ValueError
        upload = request.files.get("image")
        if upload and upload.filename:
            safe_name = secure_filename(upload.filename)
            if not safe_name:
                raise ValueError
            upload.stream.seek(0)
            with Image.open(upload.stream) as image:
                image_format = image.format
                if image_format not in ALLOWED_IMAGE_FORMATS or image.width * image.height > 20_000_000:
                    raise ValueError
                image.verify()
            image_path = uuid.uuid4().hex + ALLOWED_IMAGE_FORMATS[image_format]
            save_image(image_path, upload, upload.mimetype or "application/octet-stream")
        with connect_db() as db:
            db.execute("INSERT INTO items(code,name,category,location,quantity,minimum_stock,unit_price,notes,image_path) VALUES(?,?,?,?,?,?,?,?,?)",
                       (code, name, category,
                        request.form.get("location", "").strip(), quantity, minimum,
                        unit_price, request.form.get("notes", "").strip(), image_path))
        flash("Đã thêm mặt hàng vào kho.")
    except (ValueError, OSError, StorageError, sqlite3.IntegrityError,
            psycopg.IntegrityError, Image.DecompressionBombError):
        if image_path:
            try:
                delete_image(image_path)
            except (OSError, StorageError):
                pass
        flash("Không thể thêm: kiểm tra số liệu, giá tiền, mã trùng hoặc định dạng ảnh.")
    return redirect(url_for("index"))


@app.post("/loans")
@roles_required("admin")
def add_loan():
    try:
        item_id = int(request.form["item_id"])
        quantity = int(request.form["quantity"])
        due = date.fromisoformat(request.form["due_at"])
        borrower_name = request.form.get("borrower_name", "").strip()
        purpose = request.form.get("purpose", "").strip()
        giver = request.form.get("giver_signature", "").strip()
        receiver = request.form.get("receiver_signature", "").strip()
        if quantity < 1 or due < date.today() or not borrower_name or not purpose or not giver or not receiver:
            raise ValueError
        with connect_db() as db:
            if DATABASE_URL:
                item = db.execute("SELECT quantity FROM items WHERE id=? FOR UPDATE", (item_id,)).fetchone()
            else:
                db.execute("BEGIN IMMEDIATE")
                item = db.execute("SELECT quantity FROM items WHERE id=?", (item_id,)).fetchone()
            if not item or item["quantity"] < quantity:
                raise ValueError
            db.execute("UPDATE items SET quantity=quantity-? WHERE id=?", (quantity, item_id))
            db.execute("INSERT INTO loans(item_id,borrower_id,borrower_name,quantity,purpose,borrowed_at,due_at,issued_by,giver_signature,receiver_signature) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (item_id, current_user()["id"], borrower_name, quantity, purpose, datetime.now().isoformat(timespec="seconds"),
                        due.isoformat(), current_user()["id"], giver, receiver))
        flash("Đã tạo phiếu mượn và cập nhật tồn kho.")
    except (ValueError, KeyError, sqlite3.IntegrityError, psycopg.IntegrityError):
        flash("Không thể tạo phiếu. Kiểm tra mặt hàng, người mượn, số lượng và hạn trả.")
    return redirect(url_for("index"))


@app.post("/loans/<int:loan_id>/return")
@roles_required("admin")
def return_loan(loan_id):
    signature = request.form.get("return_signature", "").strip()
    if not signature:
        flash("Cần nhập chữ ký người nhận trả.")
        return redirect(url_for("index"))
    with connect_db() as db:
        if DATABASE_URL:
            loan = db.execute("SELECT * FROM loans WHERE id=? AND returned_at IS NULL FOR UPDATE", (loan_id,)).fetchone()
        else:
            db.execute("BEGIN IMMEDIATE")
            loan = db.execute("SELECT * FROM loans WHERE id=? AND returned_at IS NULL", (loan_id,)).fetchone()
        if not loan:
            flash("Phiếu đã được trả hoặc không tồn tại.")
        else:
            db.execute("UPDATE loans SET returned_at=?, received_by=?, return_signature=? WHERE id=?",
                       (datetime.now().isoformat(timespec="seconds"), current_user()["id"], signature, loan_id))
            db.execute("UPDATE items SET quantity=quantity+? WHERE id=?", (loan["quantity"], loan["item_id"]))
            flash("Đã ghi nhận trả thiết bị và cập nhật tồn kho.")
    return redirect(url_for("index"))


@app.get("/reports.csv")
@roles_required("admin")
def reports():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    with connect_db() as db:
        rows = db.execute("""SELECT l.*,i.code,i.name,i.category,i.unit_price,u.full_name borrower,issuer.full_name issuer,
            receiver.full_name receiver FROM loans l JOIN items i ON i.id=l.item_id
            JOIN users u ON u.id=l.borrower_id JOIN users issuer ON issuer.id=l.issued_by
            LEFT JOIN users receiver ON receiver.id=l.received_by ORDER BY l.id DESC""").fetchall()
    today_date = date.today()
    active_count = 0
    overdue_count = 0
    loan_value = 0
    writer.writerow(["BÁO CÁO THEO DÕI MƯỢN - TRẢ THIẾT BỊ"])
    writer.writerow(["Đơn vị", "Phòng thí nghiệm Điện tử số"])
    writer.writerow(["Ngày xuất", datetime.now().strftime("%d/%m/%Y %H:%M")])
    writer.writerow([])
    writer.writerow(["STT", "Mã phiếu", "Nhóm tài sản", "Mã thiết bị", "Tên thiết bị", "Người mượn", "Số lượng", "Giá đơn vị", "Giá trị ước tính", "Mục đích", "Ngày mượn", "Hạn trả", "Tình trạng", "Người giao ký", "Người nhận ký", "Ngày trả", "Người nhận trả", "Chữ ký trả"])
    for sequence, row in enumerate(rows, start=1):
        estimated_value = row["quantity"] * (row["unit_price"] or 0)
        loan_value += estimated_value
        if row["returned_at"]:
            status = "Đã trả"
        else:
            active_count += 1
            if row["due_at"] < today_date.isoformat():
                overdue_count += 1
                status = f"Quá hạn {(today_date - date.fromisoformat(row['due_at'])).days} ngày"
            else:
                status = "Đang mượn"
        writer.writerow([sequence, f"#{row['id']}", row["category"], row["code"], row["name"],
                         row["borrower_name"] or row["borrower"], row["quantity"], format_vnd(row["unit_price"]),
                         format_vnd(estimated_value) if row["unit_price"] is not None else "Chưa cập nhật",
                         row["purpose"], row["borrowed_at"].replace("T", " "), row["due_at"], status,
                         row["issuer"] + ": " + row["giver_signature"], row["receiver_signature"],
                         (row["returned_at"] or "").replace("T", " "), row["receiver"] or "", row["return_signature"]])
    writer.writerow([])
    writer.writerow(["TỔNG HỢP", "Tổng phiếu", len(rows), "Đang mượn", active_count, "Quá hạn", overdue_count,
                     "Giá trị thiết bị theo phiếu", format_vnd(loan_value)])
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=bao-cao-muon-tra.csv"
    return response


@app.get("/items/<int:item_id>/qr.png")
def item_qr(item_id):
    with connect_db() as db:
        item = db.execute("SELECT code,name FROM items WHERE id=?", (item_id,)).fetchone()
    if not item:
        abort(404)
    image = qrcode.make(f"LAB-EQUIPMENT:{item['code']}:{item['name']}")
    file_obj = io.BytesIO()
    image.save(file_obj, format="PNG")
    file_obj.seek(0)
    return send_file(file_obj, mimetype="image/png", download_name=f"QR-{item['code']}.png")


@app.get("/uploads/<path:filename>")
def uploaded_image(filename):
    try:
        with get_image_stream(filename) as source_stream:
            with Image.open(source_stream) as source:
                if source.format not in ALLOWED_IMAGE_FORMATS or source.width * source.height > 20_000_000:
                    abort(404)
                image = source.convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        font_size = max(16, min(image.width, image.height) // 24)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        label = "© Lê Bá Đăng Hoàng"
        band_height = max(34, font_size + 18)
        draw.rectangle((0, image.height - band_height, image.width, image.height), fill=(25, 25, 25, 175))
        bounds = draw.textbbox((0, 0), label, font=font)
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        draw.text(((image.width - text_width) / 2, image.height - band_height + (band_height - text_height) / 2),
                  label, fill=(255, 255, 255, 240), font=font)
        if max(image.width, image.height) > 2000:
            image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=85, method=6)
    except (FileNotFoundError, OSError, StorageError, Image.DecompressionBombError):
        abort(404)
    output.seek(0)
    response = send_file(output, mimetype="image/webp", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/loans/<int:loan_id>/slip")
def loan_slip(loan_id):
    with connect_db() as db:
        loan = db.execute("""SELECT l.*, i.code, i.name item_name,
            COALESCE(NULLIF(l.borrower_name,''),u.full_name) actual_borrower,
            issuer.full_name issuer_name, receiver.full_name receiver_name
            FROM loans l JOIN items i ON i.id=l.item_id JOIN users u ON u.id=l.borrower_id
            JOIN users issuer ON issuer.id=l.issued_by LEFT JOIN users receiver ON receiver.id=l.received_by
            WHERE l.id=?""", (loan_id,)).fetchone()
    if not loan:
        abort(404)
    if not current_user() or current_user()["role"] != "admin":
        loan = dict(loan)
        loan["giver_signature"] = "Đã ký"
        loan["receiver_signature"] = "Đã ký"
        loan["return_signature"] = "Đã ký" if loan["returned_at"] else ""
    body = """<div class="slip-tools"><a class="button" href="{{ url_for('index') }}#loans">← Quay lại danh sách</a><button class="primary" onclick="window.print()">In phiếu</button></div><article class="slip protected-copy"><div class="eyebrow">PHÒNG THÍ NGHIỆM ĐIỆN TỬ SỐ</div><h1>PHIẾU MƯỢN THIẾT BỊ</h1><div class="subtitle">Mã phiếu #{{ loan.id }} · {{ 'Đã trả' if loan.returned_at else 'Đang mượn' }}</div><div style="margin-top:25px"><div class="slip-row"><strong>Thiết bị</strong><span>{{ loan.code }} — {{ loan.item_name }}</span></div><div class="slip-row"><strong>Người mượn</strong><span>{{ loan.actual_borrower }}</span></div><div class="slip-row"><strong>Số lượng</strong><span>{{ loan.quantity }}</span></div><div class="slip-row"><strong>Mục đích</strong><span>{{ loan.purpose }}</span></div><div class="slip-row"><strong>Ngày mượn</strong><span>{{ loan.borrowed_at }}</span></div><div class="slip-row"><strong>Hạn trả</strong><span>{{ loan.due_at }}</span></div>{% if loan.returned_at %}<div class="slip-row"><strong>Ngày trả</strong><span>{{ loan.returned_at }}</span></div><div class="slip-row"><strong>Người nhận trả</strong><span>{{ loan.receiver_name or '' }}</span></div>{% endif %}</div><div class="signatures"><div class="signature">Người giao<br><strong>{{ loan.giver_signature }}</strong></div><div class="signature">Người nhận<br><strong>{{ loan.receiver_signature }}</strong></div>{% if loan.returned_at %}<div class="signature">Người nhận trả<br><strong>{{ loan.return_signature }}</strong></div>{% endif %}</div></article>"""
    return page(f"Phiếu mượn #{loan_id}", body, loan=loan)


@app.errorhandler(403)
def forbidden(_error):
    return page("Không có quyền", "<section><h1>Không có quyền truy cập</h1><p>Tài khoản của bạn không được phép thực hiện thao tác này.</p><a href='/'>Quay lại</a></section>"), 403


@app.errorhandler(404)
def not_found(_error):
    return page("Không tìm thấy", "<section><h1>Không tìm thấy trang</h1><a href='/'>Quay lại</a></section>"), 404


init_db()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
