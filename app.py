import csv
import io
import os
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import qrcode
from flask import Flask, abort, flash, g, make_response, redirect, render_template_string, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("LAB_DATABASE", BASE_DIR / "instance" / "lab.sqlite3"))
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

SCHEMA = """
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
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    borrower_id INTEGER NOT NULL REFERENCES users(id),
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

PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · Quản lý Phòng thí nghiệm Điện tử số</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#172033;background:#f3f6fb}*{box-sizing:border-box}body{margin:0}header{background:#102d55;color:white;padding:16px max(20px,calc((100% - 1180px)/2));display:flex;align-items:center;justify-content:space-between;gap:15px;flex-wrap:wrap}header a{color:#dceaff;text-decoration:none;margin-right:14px}main{max-width:1180px;margin:28px auto;padding:0 18px}.brand{font-weight:750;font-size:18px}h1{font-size:26px;margin:0 0 16px}.muted{color:#65728a}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin:18px 0}.card,section{background:white;border:1px solid #e1e7f0;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 3px 12px #243c5a0a}.metric{font-size:28px;font-weight:750;color:#154f91}input,select,textarea,button{font:inherit;padding:9px 11px;border:1px solid #cad4e2;border-radius:7px;max-width:100%}input,select,textarea{width:100%;margin:4px 0 10px}button,.button{background:#1459a3;color:white;border:0;cursor:pointer;text-decoration:none;display:inline-block;padding:9px 13px;border-radius:7px}button:hover,.button:hover{background:#0e447e}label{font-size:13px;font-weight:650;display:block}form.inline{display:inline}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;border-bottom:1px solid #e8edf3;padding:10px 8px;vertical-align:top}th{color:#53627a} .scroll{overflow:auto}.badge{padding:3px 8px;border-radius:99px;background:#e5f1ff;color:#164f8d;font-size:12px}.warn{background:#fff4dc;color:#855900}.flash{padding:10px 13px;background:#e5f4e9;border-radius:8px;margin:8px 0}.danger{color:#a33333}.small{font-size:12px}@media(max-width:650px){main{margin:18px auto}th,td{padding:8px 6px}}
</style></head><body>
<header><div><div class="brand">⚡ Phòng thí nghiệm Điện tử số</div>{% if user %}<div class="small">{{ user.full_name }} · {{ role_names[user.role] }}</div>{% endif %}</div>
<nav>{% if user %}<a href="{{ url_for('index') }}">Tổng quan</a><a href="{{ url_for('reports') }}">Báo cáo CSV</a><a href="{{ url_for('logout') }}">Đăng xuất</a>{% endif %}</nav></header>
<main>{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}{{ body|safe }}</main></body></html>"""

ROLE_NAMES = {"admin": "Quản trị viên", "staff": "Cán bộ", "lecturer": "Giảng viên", "student": "Sinh viên"}


def connect_db():
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


def init_db():
    with connect_db() as db:
        db.executescript(SCHEMA)
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
                g.user = db.execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
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
    return {"user": current_user(), "csrf_token": session["csrf_token"], "role_names": ROLE_NAMES}


def page(title, body, **context):
    html = render_template_string(body, **context)
    return render_template_string(PAGE, title=title, body=html)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("index"))
        flash("Tên đăng nhập hoặc mật khẩu không đúng.")
    body = """<section style="max-width:420px;margin:55px auto"><h1>Đăng nhập</h1><form method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><label>Tên đăng nhập</label><input name="username" required autofocus><label>Mật khẩu</label><input type="password" name="password" required><button>Đăng nhập</button></form><p class="muted small">Tạo tài khoản quản trị bằng ADMIN_USERNAME và ADMIN_PASSWORD trước lần chạy đầu.</p></section>"""
    return page("Đăng nhập", body)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    with connect_db() as db:
        items = db.execute("SELECT * FROM items ORDER BY name COLLATE NOCASE").fetchall()
        loans = db.execute("""SELECT l.*, i.code, i.name AS item_name, u.full_name AS borrower_name,
            issuer.full_name AS issuer_name FROM loans l JOIN items i ON i.id=l.item_id
            JOIN users u ON u.id=l.borrower_id JOIN users issuer ON issuer.id=l.issued_by
            WHERE l.returned_at IS NULL ORDER BY l.due_at""").fetchall()
        users = db.execute("SELECT id, full_name, role FROM users WHERE active=1 ORDER BY full_name").fetchall()
    low = [item for item in items if item["quantity"] <= item["minimum_stock"]]
    body = """<h1>Tổng quan</h1><div class="grid"><div class="card"><div class="muted">Mặt hàng</div><div class="metric">{{ items|length }}</div></div><div class="card"><div class="muted">Phiếu đang mượn</div><div class="metric">{{ loans|length }}</div></div><div class="card"><div class="muted">Sắp hết tồn</div><div class="metric">{{ low|length }}</div></div></div>
    {% if low %}<section><h2>Cảnh báo tồn kho</h2>{% for item in low %}<p><span class="badge warn">{{ item.code }}</span> {{ item.name }} — còn {{ item.quantity }}, mức tối thiểu {{ item.minimum_stock }}</p>{% endfor %}</section>{% endif %}
    <section><h2>Kho thiết bị, vật tư</h2>{% if user.role in ['admin','staff'] %}<details><summary class="button">Thêm mặt hàng</summary><form method="post" action="{{ url_for('add_item') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><div class="grid"><div><label>Mã thiết bị</label><input name="code" required></div><div><label>Tên mặt hàng</label><input name="name" required></div><div><label>Loại</label><input name="category" placeholder="Máy tính, kit, board..."></div><div><label>Vị trí</label><input name="location"></div><div><label>Số lượng</label><input type="number" min="0" name="quantity" value="1" required></div><div><label>Mức tồn tối thiểu</label><input type="number" min="0" name="minimum_stock" value="0"></div></div><label>Ghi chú</label><textarea name="notes"></textarea><button>Lưu mặt hàng</button></form></details>{% endif %}<div class="scroll"><table><thead><tr><th>Mã</th><th>Tên / Loại</th><th>Vị trí</th><th>Còn</th><th>QR</th></tr></thead><tbody>{% for item in items %}<tr><td>{{ item.code }}</td><td>{{ item.name }}<div class="muted small">{{ item.category }}{% if item.notes %} · {{ item.notes }}{% endif %}</div></td><td>{{ item.location }}</td><td>{{ item.quantity }}{% if item.quantity <= item.minimum_stock %} <span class="badge warn">Tồn thấp</span>{% endif %}</td><td><a href="{{ url_for('item_qr', item_id=item.id) }}">Tải QR</a></td></tr>{% else %}<tr><td colspan="5" class="muted">Chưa có mặt hàng. Hãy thêm mặt hàng để bắt đầu.</td></tr>{% endfor %}</tbody></table></div></section>
    {% if user.role in ['admin','staff','lecturer'] %}<section><h2>Lập phiếu mượn</h2><form method="post" action="{{ url_for('add_loan') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><div class="grid"><div><label>Thiết bị</label><select name="item_id" required>{% for item in items if item.quantity > 0 %}<option value="{{ item.id }}">{{ item.code }} — {{ item.name }} ({{ item.quantity }})</option>{% endfor %}</select></div><div><label>Người mượn</label><select name="borrower_id" required>{% for person in users %}<option value="{{ person.id }}">{{ person.full_name }} ({{ role_names[person.role] }})</option>{% endfor %}</select></div><div><label>Số lượng</label><input type="number" name="quantity" min="1" value="1" required></div><div><label>Hạn trả</label><input type="date" name="due_at" min="{{ today }}" required></div><div><label>Người giao (ký tên)</label><input name="giver_signature" required></div><div><label>Người nhận (ký tên)</label><input name="receiver_signature" required></div></div><label>Mục đích sử dụng</label><textarea name="purpose" required></textarea><button>Tạo phiếu mượn</button></form></section>{% endif %}
    <section><h2>Đang mượn</h2><div class="scroll"><table><thead><tr><th>Mã phiếu / thiết bị</th><th>Người mượn</th><th>Số lượng</th><th>Mục đích</th><th>Thời hạn / đã mượn</th><th>Ký nhận ban đầu</th><th></th></tr></thead><tbody>{% for loan in loans %}<tr><td>#{{ loan.id }}<div>{{ loan.code }} — {{ loan.item_name }}</div></td><td>{{ loan.borrower_name }}</td><td>{{ loan.quantity }}</td><td>{{ loan.purpose }}</td><td>{{ loan.due_at }}<div class="elapsed muted small" data-borrowed="{{ loan.borrowed_at }}">Đang tính…</div>{% if loan.due_at < today %}<span class="badge warn">Quá hạn</span>{% endif %}</td><td>{{ loan.giver_signature }} / {{ loan.receiver_signature }}</td><td>{% if user.role in ['admin','staff'] %}<form method="post" action="{{ url_for('return_loan', loan_id=loan.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><label>Người nhận trả</label><input name="return_signature" required><button>Ghi nhận trả</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="7" class="muted">Không có thiết bị đang mượn.</td></tr>{% endfor %}</tbody></table></div></section>
    {% if user.role == 'admin' %}<section><h2>Tạo tài khoản</h2><form method="post" action="{{ url_for('add_user') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><div class="grid"><div><label>Tên đăng nhập</label><input name="username" required></div><div><label>Họ tên</label><input name="full_name" required></div><div><label>Mật khẩu tạm</label><input type="password" name="password" minlength="10" required></div><div><label>Vai trò</label><select name="role">{% for role, name in role_names.items() %}<option value="{{ role }}">{{ name }}</option>{% endfor %}</select></div></div><button>Tạo tài khoản</button></form></section>{% endif %}
    <script>document.querySelectorAll('.elapsed').forEach(function(el){const start=new Date(el.dataset.borrowed.replace(' ','T')+'Z');function tick(){let s=Math.max(0,Math.floor((Date.now()-start.getTime())/1000)),d=Math.floor(s/86400);s%=86400;let h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);el.textContent='Đã mượn '+d+' ngày '+h+' giờ '+m+' phút'}tick();setInterval(tick,60000)})</script>"""
    return page("Tổng quan", body, items=items, loans=loans, users=users, low=low,
                today=date.today().isoformat())


@app.post("/items")
@roles_required("admin", "staff")
def add_item():
    code, name = request.form.get("code", "").strip(), request.form.get("name", "").strip()
    try:
        quantity = int(request.form.get("quantity", "1"))
        minimum = int(request.form.get("minimum_stock", "0"))
        if not code or not name or quantity < 0 or minimum < 0:
            raise ValueError
        with connect_db() as db:
            db.execute("INSERT INTO items(code,name,category,location,quantity,minimum_stock,notes) VALUES(?,?,?,?,?,?,?)",
                       (code, name, request.form.get("category", "Khác").strip() or "Khác",
                        request.form.get("location", "").strip(), quantity, minimum,
                        request.form.get("notes", "").strip()))
        flash("Đã thêm mặt hàng vào kho.")
    except (ValueError, sqlite3.IntegrityError):
        flash("Không thể thêm: hãy kiểm tra số lượng và mã thiết bị có bị trùng không.")
    return redirect(url_for("index"))


@app.post("/loans")
@roles_required("admin", "staff", "lecturer")
def add_loan():
    try:
        item_id, borrower_id = int(request.form["item_id"]), int(request.form["borrower_id"])
        quantity = int(request.form["quantity"])
        due = date.fromisoformat(request.form["due_at"])
        purpose = request.form.get("purpose", "").strip()
        giver = request.form.get("giver_signature", "").strip()
        receiver = request.form.get("receiver_signature", "").strip()
        if quantity < 1 or due < date.today() or not purpose or not giver or not receiver:
            raise ValueError
        with connect_db() as db:
            db.execute("BEGIN IMMEDIATE")
            item = db.execute("SELECT quantity FROM items WHERE id=?", (item_id,)).fetchone()
            borrower = db.execute("SELECT id FROM users WHERE id=? AND active=1", (borrower_id,)).fetchone()
            if not item or not borrower or item["quantity"] < quantity:
                raise ValueError
            db.execute("UPDATE items SET quantity=quantity-? WHERE id=?", (quantity, item_id))
            db.execute("INSERT INTO loans(item_id,borrower_id,quantity,purpose,borrowed_at,due_at,issued_by,giver_signature,receiver_signature) VALUES(?,?,?,?,?,?,?,?,?)",
                       (item_id, borrower_id, quantity, purpose, datetime.now().isoformat(timespec="seconds"),
                        due.isoformat(), current_user()["id"], giver, receiver))
        flash("Đã tạo phiếu mượn và cập nhật tồn kho.")
    except (ValueError, KeyError, sqlite3.IntegrityError):
        flash("Không thể tạo phiếu. Kiểm tra mặt hàng, người mượn, số lượng và hạn trả.")
    return redirect(url_for("index"))


@app.post("/loans/<int:loan_id>/return")
@roles_required("admin", "staff")
def return_loan(loan_id):
    signature = request.form.get("return_signature", "").strip()
    if not signature:
        flash("Cần nhập chữ ký người nhận trả.")
        return redirect(url_for("index"))
    with connect_db() as db:
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


@app.post("/users")
@roles_required("admin")
def add_user():
    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "student")
    if not username or not full_name or len(password) < 10 or role not in ROLE_NAMES:
        flash("Kiểm tra thông tin; mật khẩu cần ít nhất 10 ký tự.")
    else:
        try:
            with connect_db() as db:
                db.execute("INSERT INTO users(username,full_name,password_hash,role) VALUES(?,?,?,?)",
                           (username, full_name, generate_password_hash(password), role))
            flash("Đã tạo tài khoản. Gửi thông tin đăng nhập cho người dùng qua kênh an toàn.")
        except sqlite3.IntegrityError:
            flash("Tên đăng nhập đã tồn tại.")
    return redirect(url_for("index"))


@app.get("/reports.csv")
@login_required
def reports():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Mã phiếu", "Mã thiết bị", "Thiết bị", "Người mượn", "Số lượng", "Mục đích", "Ngày mượn", "Hạn trả", "Người giao ký", "Người nhận ký", "Ngày trả", "Người nhận trả", "Chữ ký trả"])
    with connect_db() as db:
        rows = db.execute("""SELECT l.*,i.code,i.name,u.full_name borrower,issuer.full_name issuer,
            receiver.full_name receiver FROM loans l JOIN items i ON i.id=l.item_id
            JOIN users u ON u.id=l.borrower_id JOIN users issuer ON issuer.id=l.issued_by
            LEFT JOIN users receiver ON receiver.id=l.received_by ORDER BY l.id DESC""").fetchall()
    for row in rows:
        writer.writerow([row["id"], row["code"], row["name"], row["borrower"], row["quantity"], row["purpose"], row["borrowed_at"], row["due_at"], row["issuer"] + ": " + row["giver_signature"], row["receiver_signature"], row["returned_at"] or "", row["receiver"] or "", row["return_signature"]])
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=bao-cao-muon-tra.csv"
    return response


@app.get("/items/<int:item_id>/qr.png")
@login_required
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


@app.errorhandler(403)
def forbidden(_error):
    return page("Không có quyền", "<section><h1>Không có quyền truy cập</h1><p>Tài khoản của bạn không được phép thực hiện thao tác này.</p><a href='/'>Quay lại</a></section>"), 403


@app.errorhandler(404)
def not_found(_error):
    return page("Không tìm thấy", "<section><h1>Không tìm thấy trang</h1><a href='/'>Quay lại</a></section>"), 404


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
