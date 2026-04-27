from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
import calendar
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DATABASE = Path("household.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'user',
        color TEXT DEFAULT '#0d6efd',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        event_date TEXT NOT NULL,
        event_time TEXT,
        location TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS event_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        user_id INTEGER,
        comment TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(event_id) REFERENCES events(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS shopping_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT NOT NULL,
        quantity TEXT,
        added_by INTEGER,
        is_done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(added_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task TEXT NOT NULL,
        responsible_user INTEGER,
        due_date TEXT,
        priority TEXT DEFAULT 'Normal',
        status TEXT DEFAULT 'Pending',
        repeat_type TEXT DEFAULT 'None',
        is_done INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(responsible_user) REFERENCES users(id),
        FOREIGN KEY(created_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );
    """)

    # Upgrade older DBs created by v1
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "password_hash" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "role" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")

    event_columns = [row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "description" not in event_columns:
        conn.execute("ALTER TABLE events ADD COLUMN description TEXT")

    shopping_columns = [row["name"] for row in conn.execute("PRAGMA table_info(shopping_items)").fetchall()]
    if "category" not in shopping_columns:
        conn.execute("ALTER TABLE shopping_items ADD COLUMN category TEXT DEFAULT 'General'")

    todo_columns = [row["name"] for row in conn.execute("PRAGMA table_info(todos)").fetchall()]
    if "status" not in todo_columns:
        conn.execute("ALTER TABLE todos ADD COLUMN status TEXT DEFAULT 'Pending'")
    if "repeat_type" not in todo_columns:
        conn.execute("ALTER TABLE todos ADD COLUMN repeat_type TEXT DEFAULT 'None'")

    # First-time default admin
    user_count = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    if user_count == 0:
        conn.execute("""
            INSERT INTO users (name, password_hash, role, color, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("admin", generate_password_hash("admin123"), "admin", "#dc3545", now()))

    conn.commit()
    conn.close()


def current_user():
    if not session.get("user_id"):
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user


def current_user_id():
    user = current_user()
    return user["id"] if user else None


def is_admin():
    user = current_user()
    return bool(user and user["role"] == "admin")


def can_delete(created_by):
    user = current_user()
    if not user:
        return False
    return user["role"] == "admin" or user["id"] == created_by


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            flash("Admin access required.", "warning")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return {
        "users": users,
        "active_user": current_user(),
        "is_admin": is_admin,
        "can_delete": can_delete
    }




@app.route("/search")
@login_required
def search_page():
    search = request.args.get("q", "").strip()
    results = {
        "events": [],
        "shopping": [],
        "todos": [],
        "notices": []
    }

    if search:
        like = f"%{search}%"
        conn = get_db()

        results["events"] = conn.execute("""
            SELECT e.*, u.name AS user_name
            FROM events e
            LEFT JOIN users u ON e.created_by = u.id
            WHERE e.title LIKE ? OR e.location LIKE ? OR e.description LIKE ?
            ORDER BY e.event_date, e.event_time
            LIMIT 50
        """, (like, like, like)).fetchall()

        results["shopping"] = conn.execute("""
            SELECT s.*, u.name AS user_name
            FROM shopping_items s
            LEFT JOIN users u ON s.added_by = u.id
            WHERE s.item LIKE ? OR s.quantity LIKE ? OR s.category LIKE ?
            ORDER BY s.is_done, s.category, s.created_at DESC
            LIMIT 50
        """, (like, like, like)).fetchall()

        results["todos"] = conn.execute("""
            SELECT t.*, ru.name AS responsible_name, cu.name AS creator_name
            FROM todos t
            LEFT JOIN users ru ON t.responsible_user = ru.id
            LEFT JOIN users cu ON t.created_by = cu.id
            WHERE t.task LIKE ? OR t.priority LIKE ? OR t.status LIKE ? OR t.repeat_type LIKE ?
            ORDER BY t.is_done, t.due_date IS NULL, t.due_date
            LIMIT 50
        """, (like, like, like, like)).fetchall()

        results["notices"] = conn.execute("""
            SELECT n.*, u.name AS user_name
            FROM notices n
            LEFT JOIN users u ON n.created_by = u.id
            WHERE n.title LIKE ? OR n.message LIKE ?
            ORDER BY n.created_at DESC
            LIMIT 50
        """, (like, like)).fetchall()

        conn.close()

    return render_template("search.html", search=search, results=results)

@app.route("/offline")
def offline():
    return render_template("offline.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        conn.close()

        if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['name']}.", "success")
            return redirect(url_for("dashboard"))

        flash("Incorrect username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    selected_date = request.args.get("date")
    today = date.today()

    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
    except ValueError:
        year, month = today.year, today.month

    if month < 1:
        month = 12
        year -= 1
    if month > 12:
        month = 1
        year += 1

    conn = get_db()

    month_start = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    month_end = f"{year:04d}-{month:02d}-{last_day:02d}"

    events = conn.execute("""
        SELECT e.*, u.name AS user_name, u.color AS user_color
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.event_date BETWEEN ? AND ?
        ORDER BY e.event_date, e.event_time
    """, (month_start, month_end)).fetchall()

    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event["event_date"], []).append(event)

    calendar_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)

    selected_events = []
    if selected_date:
        selected_events = conn.execute("""
            SELECT e.*, u.name AS user_name, u.color AS user_color
            FROM events e
            LEFT JOIN users u ON e.created_by = u.id
            WHERE e.event_date = ?
            ORDER BY e.event_time
        """, (selected_date,)).fetchall()

    today_key = today.strftime("%Y-%m-%d")
    week_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    today_events = conn.execute("""
        SELECT e.*, u.name AS user_name
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.event_date = ?
        ORDER BY e.event_time
    """, (today_key,)).fetchall()

    week_events = conn.execute("""
        SELECT e.*, u.name AS user_name
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.event_date BETWEEN ? AND ?
        ORDER BY e.event_date, e.event_time
        LIMIT 8
    """, (today_key, week_end)).fetchall()

    overdue_todos = conn.execute("""
        SELECT t.*, ru.name AS responsible_name
        FROM todos t
        LEFT JOIN users ru ON t.responsible_user = ru.id
        WHERE t.is_done = 0 AND t.due_date IS NOT NULL AND t.due_date < date('now')
        ORDER BY t.due_date
        LIMIT 8
    """).fetchall()

    shopping = conn.execute("""
        SELECT s.*, u.name AS user_name
        FROM shopping_items s
        LEFT JOIN users u ON s.added_by = u.id
        WHERE s.is_done = 0
        ORDER BY s.category, s.created_at DESC
        LIMIT 6
    """).fetchall()

    todos = conn.execute("""
        SELECT t.*, ru.name AS responsible_name
        FROM todos t
        LEFT JOIN users ru ON t.responsible_user = ru.id
        WHERE t.is_done = 0
        ORDER BY 
            CASE t.priority WHEN 'High' THEN 1 WHEN 'Normal' THEN 2 ELSE 3 END,
            t.due_date IS NULL,
            t.due_date
        LIMIT 6
    """).fetchall()

    notices = conn.execute("""
        SELECT n.*, u.name AS user_name
        FROM notices n
        LEFT JOIN users u ON n.created_by = u.id
        ORDER BY n.created_at DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    prev_month = month - 1
    prev_year = year
    next_month = month + 1
    next_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    if next_month > 12:
        next_month = 1
        next_year += 1

    return render_template(
        "dashboard.html",
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        calendar_weeks=calendar_weeks,
        events_by_date=events_by_date,
        selected_date=selected_date,
        selected_events=selected_events,
        shopping=shopping,
        todos=todos,
        today_events=today_events,
        week_events=week_events,
        overdue_todos=overdue_todos,
        notices=notices,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        today=today
    )


@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users_page():
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        color = request.form.get("color", "#0d6efd")

        if not name or not password:
            flash("User name and password are required.", "warning")
        elif role not in ["admin", "user"]:
            flash("Invalid role.", "warning")
        else:
            try:
                conn.execute(
                    "INSERT INTO users (name, password_hash, role, color, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, generate_password_hash(password), role, color, now())
                )
                conn.commit()
                flash("User added.", "success")
            except sqlite3.IntegrityError:
                flash("That user already exists.", "warning")

    household_users = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return render_template("users.html", household_users=household_users)


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user_id():
        flash("You cannot delete your own logged-in user.", "warning")
        return redirect(url_for("users_page"))

    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("User deleted.", "success")
    return redirect(url_for("users_page"))


@app.route("/calendar", methods=["GET", "POST"])
@login_required
def calendar_page():
    conn = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        event_date = request.form.get("event_date")
        event_time = request.form.get("event_time")
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        if not title or not event_date:
            flash("Title and date are required.", "warning")
        else:
            conn.execute("""
                INSERT INTO events (title, event_date, event_time, location, description, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, event_date, event_time, location, description, current_user_id(), now()))
            conn.commit()
            flash("Event added.", "success")

    events = conn.execute("""
        SELECT e.*, u.name AS user_name, u.color AS user_color,
               COUNT(c.id) AS comment_count
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        LEFT JOIN event_comments c ON c.event_id = e.id
        GROUP BY e.id
        ORDER BY e.event_date, e.event_time
    """).fetchall()

    conn.close()
    return render_template("calendar.html", events=events)


@app.route("/event/<int:event_id>", methods=["GET", "POST"])
@login_required
def event_detail(event_id):
    conn = get_db()
    if request.method == "POST":
        comment = request.form.get("comment", "").strip()
        if comment:
            conn.execute("""
                INSERT INTO event_comments (event_id, user_id, comment, created_at)
                VALUES (?, ?, ?, ?)
            """, (event_id, current_user_id(), comment, now()))
            conn.commit()
            flash("Comment added.", "success")

    event = conn.execute("""
        SELECT e.*, u.name AS user_name, u.color AS user_color
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.id = ?
    """, (event_id,)).fetchone()

    comments = conn.execute("""
        SELECT c.*, u.name AS user_name, u.color AS user_color
        FROM event_comments c
        LEFT JOIN users u ON c.user_id = u.id
        WHERE c.event_id = ?
        ORDER BY c.created_at DESC
    """, (event_id,)).fetchall()
    conn.close()

    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("calendar_page"))

    return render_template("event_detail.html", event=event, comments=comments)


@app.route("/event/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        flash("Event not found.", "danger")
        return redirect(url_for("calendar_page"))

    if not can_delete(event["created_by"]):
        conn.close()
        flash("You can only delete items you created.", "warning")
        return redirect(url_for("event_detail", event_id=event_id))

    conn.execute("DELETE FROM event_comments WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    flash("Event deleted.", "success")
    return redirect(url_for("calendar_page"))


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    conn = get_db()
    comment = conn.execute("SELECT * FROM event_comments WHERE id = ?", (comment_id,)).fetchone()
    if not comment:
        conn.close()
        flash("Comment not found.", "danger")
        return redirect(url_for("calendar_page"))

    if not can_delete(comment["user_id"]):
        conn.close()
        flash("You can only delete comments you created.", "warning")
        return redirect(url_for("event_detail", event_id=comment["event_id"]))

    event_id = comment["event_id"]
    conn.execute("DELETE FROM event_comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()
    flash("Comment deleted.", "success")
    return redirect(url_for("event_detail", event_id=event_id))


@app.route("/shopping", methods=["GET", "POST"])
@login_required
def shopping_page():
    conn = get_db()
    if request.method == "POST":
        item = request.form.get("item", "").strip()
        quantity = request.form.get("quantity", "").strip()
        category = request.form.get("category", "General").strip() or "General"
        if not item:
            flash("Shopping item is required.", "warning")
        else:
            conn.execute("""
                INSERT INTO shopping_items (item, quantity, category, added_by, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (item, quantity, category, current_user_id(), now()))
            conn.commit()
            flash("Shopping item added.", "success")

    items = conn.execute("""
        SELECT s.*, u.name AS user_name
        FROM shopping_items s
        LEFT JOIN users u ON s.added_by = u.id
        ORDER BY s.is_done, s.category, s.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("shopping.html", items=items)


@app.route("/shopping/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_shopping(item_id):
    conn = get_db()
    conn.execute("UPDATE shopping_items SET is_done = CASE WHEN is_done = 1 THEN 0 ELSE 1 END WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("shopping_page"))


@app.route("/shopping/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_shopping(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        flash("Shopping item not found.", "danger")
        return redirect(url_for("shopping_page"))

    if not can_delete(item["added_by"]):
        conn.close()
        flash("You can only delete items you created.", "warning")
        return redirect(url_for("shopping_page"))

    conn.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    flash("Shopping item deleted.", "success")
    return redirect(url_for("shopping_page"))


@app.route("/todo", methods=["GET", "POST"])
@login_required
def todo_page():
    conn = get_db()
    if request.method == "POST":
        task = request.form.get("task", "").strip()
        responsible_user = request.form.get("responsible_user") or None
        due_date = request.form.get("due_date") or None
        priority = request.form.get("priority", "Normal")
        status = request.form.get("status", "Pending")
        repeat_type = request.form.get("repeat_type", "None")
        if not task:
            flash("Task is required.", "warning")
        else:
            is_done = 1 if status == "Done" else 0
            conn.execute("""
                INSERT INTO todos (task, responsible_user, due_date, priority, status, repeat_type, is_done, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (task, responsible_user, due_date, priority, status, repeat_type, is_done, current_user_id(), now()))
            conn.commit()
            flash("To-do added.", "success")

    todos = conn.execute("""
        SELECT t.*, ru.name AS responsible_name, cu.name AS creator_name
        FROM todos t
        LEFT JOIN users ru ON t.responsible_user = ru.id
        LEFT JOIN users cu ON t.created_by = cu.id
        ORDER BY t.is_done,
            CASE t.priority WHEN 'High' THEN 1 WHEN 'Normal' THEN 2 ELSE 3 END,
            t.due_date IS NULL,
            t.due_date
    """).fetchall()
    conn.close()
    return render_template("todo.html", todos=todos)


@app.route("/todo/<int:todo_id>/toggle", methods=["POST"])
@login_required
def toggle_todo(todo_id):
    conn = get_db()
    todo = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()

    if todo and todo["is_done"] == 0:
        conn.execute("UPDATE todos SET is_done = 1, status = 'Done' WHERE id = ?", (todo_id,))

        repeat_type = todo["repeat_type"] or "None"
        if repeat_type != "None" and todo["due_date"]:
            old_due = datetime.strptime(todo["due_date"], "%Y-%m-%d").date()
            if repeat_type == "Daily":
                next_due = old_due + timedelta(days=1)
            elif repeat_type == "Weekly":
                next_due = old_due + timedelta(days=7)
            elif repeat_type == "Monthly":
                next_due = old_due + timedelta(days=30)
            else:
                next_due = None

            if next_due:
                conn.execute("""
                    INSERT INTO todos (task, responsible_user, due_date, priority, status, repeat_type, is_done, created_by, created_at)
                    VALUES (?, ?, ?, ?, 'Pending', ?, 0, ?, ?)
                """, (
                    todo["task"],
                    todo["responsible_user"],
                    next_due.strftime("%Y-%m-%d"),
                    todo["priority"],
                    repeat_type,
                    todo["created_by"],
                    now()
                ))
    else:
        conn.execute("UPDATE todos SET is_done = 0, status = 'Pending' WHERE id = ?", (todo_id,))

    conn.commit()
    conn.close()
    return redirect(url_for("todo_page"))


@app.route("/todo/<int:todo_id>/delete", methods=["POST"])
@login_required
def delete_todo(todo_id):
    conn = get_db()
    todo = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if not todo:
        conn.close()
        flash("Task not found.", "danger")
        return redirect(url_for("todo_page"))

    if not can_delete(todo["created_by"]):
        conn.close()
        flash("You can only delete tasks you created.", "warning")
        return redirect(url_for("todo_page"))

    conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    flash("Task deleted.", "success")
    return redirect(url_for("todo_page"))



@app.route("/notifications")
@login_required
def notifications_page():
    return render_template("notifications.html")


@app.route("/api/notifications")
@login_required
def api_notifications():
    conn = get_db()
    user_id = current_user_id()

    events = conn.execute("""
        SELECT e.*, u.name AS user_name
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.event_date BETWEEN date('now') AND date('now', '+1 day')
        ORDER BY e.event_date, e.event_time
    """).fetchall()

    todos = conn.execute("""
        SELECT t.*, ru.name AS responsible_name
        FROM todos t
        LEFT JOIN users ru ON t.responsible_user = ru.id
        WHERE t.is_done = 0
          AND (
                t.due_date <= date('now')
                OR t.responsible_user = ?
              )
        ORDER BY t.due_date
    """, (user_id,)).fetchall()

    conn.close()

    payload = {
        "events": [
            {
                "id": event["id"],
                "title": event["title"],
                "date": event["event_date"],
                "time": event["event_time"],
                "location": event["location"],
                "created_by": event["user_name"] or "Unknown",
                "url": url_for("event_detail", event_id=event["id"])
            }
            for event in events
        ],
        "todos": [
            {
                "id": todo["id"],
                "task": todo["task"],
                "due_date": todo["due_date"],
                "responsible": todo["responsible_name"] or "Unassigned",
                "priority": todo["priority"],
                "url": url_for("todo_page")
            }
            for todo in todos
        ]
    }

    return jsonify(payload)


@app.route("/notice/add", methods=["POST"])
@login_required
def add_notice():
    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()

    if not title or not message:
        flash("Notice title and message are required.", "warning")
        return redirect(url_for("dashboard"))

    conn = get_db()
    conn.execute("""
        INSERT INTO notices (title, message, created_by, created_at)
        VALUES (?, ?, ?, ?)
    """, (title, message, current_user_id(), now()))
    conn.commit()
    conn.close()

    flash("Notice added.", "success")
    return redirect(url_for("dashboard"))


@app.route("/notice/<int:notice_id>/delete", methods=["POST"])
@login_required
def delete_notice(notice_id):
    conn = get_db()
    notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()

    if not notice:
        conn.close()
        flash("Notice not found.", "danger")
        return redirect(url_for("dashboard"))

    if not can_delete(notice["created_by"]):
        conn.close()
        flash("You can only delete notices you created.", "warning")
        return redirect(url_for("dashboard"))

    conn.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    conn.commit()
    conn.close()

    flash("Notice deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/event/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()

    if not event:
        conn.close()
        flash("Event not found.", "danger")
        return redirect(url_for("calendar_page"))

    if not can_delete(event["created_by"]):
        conn.close()
        flash("You can only edit events you created.", "warning")
        return redirect(url_for("event_detail", event_id=event_id))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        event_date = request.form.get("event_date")
        event_time = request.form.get("event_time")
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not event_date:
            flash("Title and date are required.", "warning")
        else:
            conn.execute("""
                UPDATE events
                SET title = ?, event_date = ?, event_time = ?, location = ?, description = ?
                WHERE id = ?
            """, (title, event_date, event_time, location, description, event_id))
            conn.commit()
            conn.close()
            flash("Event updated.", "success")
            return redirect(url_for("event_detail", event_id=event_id))

    conn.close()
    return render_template("edit_event.html", event=event)


@app.route("/shopping/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_shopping(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM shopping_items WHERE id = ?", (item_id,)).fetchone()

    if not item:
        conn.close()
        flash("Shopping item not found.", "danger")
        return redirect(url_for("shopping_page"))

    if not can_delete(item["added_by"]):
        conn.close()
        flash("You can only edit items you created.", "warning")
        return redirect(url_for("shopping_page"))

    if request.method == "POST":
        item_name = request.form.get("item", "").strip()
        quantity = request.form.get("quantity", "").strip()
        category = request.form.get("category", "General").strip() or "General"

        if not item_name:
            flash("Shopping item is required.", "warning")
        else:
            conn.execute("""
                UPDATE shopping_items
                SET item = ?, quantity = ?, category = ?
                WHERE id = ?
            """, (item_name, quantity, category, item_id))
            conn.commit()
            conn.close()
            flash("Shopping item updated.", "success")
            return redirect(url_for("shopping_page"))

    conn.close()
    return render_template("edit_shopping.html", item=item)


@app.route("/todo/<int:todo_id>/edit", methods=["GET", "POST"])
@login_required
def edit_todo(todo_id):
    conn = get_db()
    todo = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()

    if not todo:
        conn.close()
        flash("Task not found.", "danger")
        return redirect(url_for("todo_page"))

    if not can_delete(todo["created_by"]):
        conn.close()
        flash("You can only edit tasks you created.", "warning")
        return redirect(url_for("todo_page"))

    if request.method == "POST":
        task = request.form.get("task", "").strip()
        responsible_user = request.form.get("responsible_user") or None
        due_date = request.form.get("due_date") or None
        priority = request.form.get("priority", "Normal")
        status = request.form.get("status", "Pending")
        repeat_type = request.form.get("repeat_type", "None")
        is_done = 1 if status == "Done" else 0

        if not task:
            flash("Task is required.", "warning")
        else:
            conn.execute("""
                UPDATE todos
                SET task = ?, responsible_user = ?, due_date = ?, priority = ?, status = ?, repeat_type = ?, is_done = ?
                WHERE id = ?
            """, (task, responsible_user, due_date, priority, status, repeat_type, is_done, todo_id))
            conn.commit()
            conn.close()
            flash("Task updated.", "success")
            return redirect(url_for("todo_page"))

    users_for_form = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return render_template("edit_todo.html", todo=todo, users_for_form=users_for_form)

@app.route("/phase-2")
@login_required
def phase_2():
    return render_template("phase_2.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    init_db()
