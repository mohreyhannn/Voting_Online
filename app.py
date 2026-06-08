import json

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection


app = Flask(__name__)
app.secret_key = "suara-kita-secret-key"

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()

        # Cek admin dulu
        cur.execute(
            "SELECT * FROM admins WHERE username=%s",
            (username,)
        )
        admin = cur.fetchone()

        if admin and admin["password"] == password:
            session.clear()
            session["admin"] = admin["username"]

            cur.close()
            conn.close()

            flash("Selamat datang admin", "success")
            return redirect("/admin")

        # Kalau bukan admin, cek user
        cur.execute(
            "SELECT * FROM users WHERE username=%s",
            (username,)
        )
        user = cur.fetchone()

        if user and user["password"] == password:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            cur.close()
            conn.close()

            flash("Silahkan memilih, jangan golput ya", "success")
            return redirect("/home")

        cur.close()
        conn.close()

        flash("Username atau password salah, inget-inget lagi deh", "danger")
        return redirect("/")

    return render_template("login.html")


@app.route("/home")
def home():

    if "user_id" not in session:
        return redirect("/")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM polls")
    total_polls = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) FROM votes")
    total_votes = cur.fetchone()["count"]

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        total_polls=total_polls,
        total_votes=total_votes
    )

@app.route("/polls")
def polls():

    if "user_id" not in session:
        return redirect("/")

    if "admin" in session:
        return redirect("/admin")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM polls ORDER BY id DESC;")
    polls = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("polls.html", polls=polls)


@app.route("/vote/<int:poll_id>")
def vote(poll_id):

    if "admin" in session:
        return redirect("/admin")

    if "user_id" not in session:
        return redirect("/")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM polls WHERE id = %s;", (poll_id,))
    poll = cur.fetchone()

    if poll is None:
        cur.close()
        conn.close()
        return "Polling tidak ditemukan"

    cur.execute("SELECT * FROM options WHERE poll_id = %s;", (poll_id,))
    options = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("vote.html", poll=poll, options=options)


@app.route("/submit-vote", methods=["POST"])
def submit_vote():

    if "user_id" not in session:
        return redirect("/")

    poll_id = request.form.get("poll_id")
    option_id = request.form.get("option_id")
    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # cek apakah user sudah voting pada polling ini

    cur.execute("""
        SELECT votes.id
        FROM votes
        JOIN options
            ON votes.option_id = options.id
        WHERE options.poll_id = %s
        AND votes.user_id = %s
    """,
    (poll_id, user_id))

    existing_vote = cur.fetchone()

    if existing_vote:

        cur.close()
        conn.close()

        flash(
            "Lau Udeh polling, jangan maruk.",
            "warning"
        )

        return render_template(
            "already_voted.html"
        )

    cur.execute(
        """
        INSERT INTO votes(
            option_id,
            user_id
        )
        VALUES(%s,%s)
        """,
        (
            option_id,
            user_id
        )
    )

    conn.commit()

    cur.close()
    conn.close()

    flash(
        "Voting berhasil yeee.",
        "success"
    )

    return redirect(
        url_for(
            "result",
            poll_id=poll_id
        )
    )

@app.route("/admin")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM polls ORDER BY id DESC")
    polls = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM polls")
    total_polls = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) FROM options")
    total_options = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) FROM votes")
    total_votes = cur.fetchone()["count"]

    cur.close()
    conn.close()

    return render_template(
        "admin/dashboard.html",
        polls=polls,
        total_polls=total_polls,
        total_options=total_options,
        total_votes=total_votes
    )

@app.route("/result/<int:poll_id>")
def result(poll_id):

    if "user_id" not in session and "admin" not in session:
        return redirect("/")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM polls WHERE id = %s;", (poll_id,))
    poll = cur.fetchone()

    cur.execute("""
        SELECT 
            options.id,
            options.option_text,
            COUNT(votes.id) AS total_votes
        FROM options
        LEFT JOIN votes ON options.id = votes.option_id
        WHERE options.poll_id = %s
        GROUP BY options.id, options.option_text
        ORDER BY options.id;
    """, (poll_id,))

    results = cur.fetchall()
    total_votes = sum(item["total_votes"] for item in results)

    for item in results:
        item["percentage"] = round((item["total_votes"] / total_votes) * 100, 1) if total_votes > 0 else 0

    labels = [item["option_text"] for item in results]
    data_votes = [item["total_votes"] for item in results]
    labels_json = json.dumps(labels)
    data_votes_json = json.dumps(data_votes)

    cur.close()
    conn.close()

    return render_template(
    "result.html",
    poll=poll,
    results=results,
    total_votes=total_votes,
    labels_json=labels_json,
    data_votes_json=data_votes_json
)

@app.route("/logout")
def logout():
    session.clear()
    flash("Lau ude Logout yee", "success")
    return redirect("/")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM admins
            WHERE username=%s
            """,
            (username,)
        )

        admin = cur.fetchone()

        cur.close()
        conn.close()

        if admin and admin["password"] == password:

            session["admin"] = username

            flash(
                "Lau login jadi admin yee",
                "success"
            )

            return redirect("/admin")

        flash(
            "Username atau Password salah, coba lagi yee",
            "danger"
        )

    return render_template(
        "admin/login.html"
    )

@app.route("/admin/add", methods=["GET", "POST"])
def add_poll():

    if "admin" not in session:
        return redirect("/")

    if request.method == "POST":

        question = request.form["question"]

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO polls(question)
            VALUES(%s)
            """,
            (question,)
        )

        conn.commit()

        cur.close()
        conn.close()

        flash("Polling baru berhasil ditambahkan.", "success")
        return redirect("/admin")

    return render_template(
        "admin/add_poll.html"
    )

@app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
def edit_poll(id):

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":

        question = request.form["question"]

        cur.execute("""
            UPDATE polls
            SET question = %s
            WHERE id = %s
        """, (question, id))

        conn.commit()

        cur.close()
        conn.close()

        flash("Pertanyaan polling berhasil diperbarui.", "success")
        return redirect("/admin")

    cur.execute("""
        SELECT *
        FROM polls
        WHERE id = %s
    """, (id,))

    poll = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "admin/edit_poll.html",
        poll=poll
    )

@app.route("/admin/delete/<int:id>")
def delete_poll(id):

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM polls
        WHERE id = %s
    """, (id,))

    conn.commit()

    cur.close()
    conn.close()

    flash("Polling berhasil dihapus.", "danger")
    return redirect("/admin")

@app.route("/admin/options/<int:poll_id>")
def manage_options(poll_id):

    if "admin" not in session:
        return redirect("/")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM polls WHERE id=%s",
        (poll_id,)
    )

    poll = cur.fetchone()

    cur.execute(
        """
        SELECT *
        FROM options
        WHERE poll_id=%s
        ORDER BY id
        """,
        (poll_id,)
    )

    options = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "admin/options.html",
        poll=poll,
        options=options
    )

@app.route(
    "/admin/options/add/<int:poll_id>",
    methods=["POST"]
)
def add_option(poll_id):

    if "admin" not in session:
        return redirect("/")

    option_text = request.form["option_text"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO options(
            poll_id,
            option_text
        )
        VALUES(%s,%s)
        """,
        (poll_id, option_text)
    )

    conn.commit()

    cur.close()
    conn.close()

    flash(
        "Opsi berhasil ditambahkan",
        "success"
    )

    return redirect(
        f"/admin/options/{poll_id}"
    )

@app.route("/admin/options/delete/<int:id>")
def delete_option(id):

    if "admin" not in session:
        return redirect("/")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT poll_id FROM options WHERE id=%s",
        (id,)
    )

    option = cur.fetchone()

    if option is None:
        cur.close()
        conn.close()
        flash("Opsi tidak ditemukan", "danger")
        return redirect("/admin")

    poll_id = option["poll_id"]

    cur.execute(
        "DELETE FROM options WHERE id=%s",
        (id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    flash("Opsi berhasil dihapus", "danger")
    return redirect(f"/admin/options/{poll_id}")

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Konfirmasi password tidak sesuai", "danger")
            return redirect("/register")

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=%s OR email=%s",
            (username, email)
        )

        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            conn.close()
            flash("Username atau email sudah digunakan", "danger")
            return redirect("/register")

        cur.execute(
            """
            INSERT INTO users(username, email, password)
            VALUES(%s, %s, %s)
            """,
            (username, email, password)
        )

        conn.commit()

        cur.close()
        conn.close()

        flash("Anaji akun baru. Silakan login.", "success")
        return redirect("/")

    return render_template("register.html")


if __name__ == "__main__":
    app.run(debug=True)