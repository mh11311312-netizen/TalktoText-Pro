"""
Flask entry point. This wires together the four helper modules (ai_engine,
database, auth, exports) and exposes the routes the front-end talks to.

The one thing worth knowing: transcribing audio can take a while, so /upload
kicks the work off on a background thread and hands the browser a job id. The
page then polls /status/<job_id> to move the progress bar along, and jumps to
the results page once the job reports done.

Run it with `python app.py`, then open http://127.0.0.1:5000.
"""

import os
import threading
import traceback
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_file, send_from_directory)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

import ai_engine
import database
import exports
from auth import register_user, verify_user, login_required

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
    static_url_path="/static"
)
raw_secret = (os.getenv("SECRET_KEY") or "").strip()
app.secret_key = raw_secret if raw_secret else "talktotext-pro-secret-key-production-87654321"
app.config["SECRET_KEY"] = app.secret_key


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/style.css")
def serve_root_style():
    return send_from_directory(STATIC_DIR, "style.css")


@app.route("/script.js")
def serve_root_script():
    return send_from_directory(STATIC_DIR, "script.js")


def _get_dir(name):
    # In Vercel serverless environment, use /tmp directly
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        tmp_path = os.path.join("/tmp", name)
        try:
            os.makedirs(tmp_path, exist_ok=True)
            return tmp_path
        except Exception:
            return "/tmp"

    local_path = os.path.join(BASE_DIR, name)
    try:
        os.makedirs(local_path, exist_ok=True)
        test_file = os.path.join(local_path, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return local_path
    except Exception:
        tmp_path = os.path.join("/tmp", name)
        try:
            os.makedirs(tmp_path, exist_ok=True)
            return tmp_path
        except Exception:
            return "/tmp"


UPLOAD_DIR = _get_dir("uploads")
JOBS_DIR = _get_dir("jobs")
ALLOWED = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg"}

# Track in-flight jobs in memory and /tmp cache for serverless environments.
JOBS = {}


def get_job_state(job_id):
    if job_id in JOBS:
        return JOBS[job_id]
    job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(job_file):
        try:
            import json
            with open(job_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def update_job_state(job_id, data):
    JOBS[job_id] = data
    job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
    try:
        import json
        with open(job_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def process_meeting(job_id, username, file_path, title, language, output_language):
    # Walks the audio through the whole pipeline and updates progress.
    def step(percent, message):
        job = get_job_state(job_id) or {}
        job["progress"] = percent
        job["message"] = message
        update_job_state(job_id, job)

    try:
        step(15, "Transcribing audio...")
        transcription = ai_engine.smart_transcribe(file_path, language)
        raw_text = transcription["text"]
        if not raw_text.strip():
            raise ValueError("No speech was detected in the audio.")

        step(40, "Translating to English...")
        english_text, was_translated = ai_engine.detect_and_translate(
            raw_text, transcription.get("language", language)
        )

        step(55, "Cleaning & optimizing text...")
        optimized = ai_engine.optimize_text(english_text)

        step(72, "Generating meeting notes...")
        notes = ai_engine.generate_notes(optimized, output_language)

        # No title from the user? Ask the model to name it.
        if not title or title.strip().lower() in ("", "untitled meeting"):
            try:
                title = ai_engine.generate_title(optimized)
            except Exception:
                title = "Untitled Meeting"

        step(85, "Building topic chapters...")
        chapters = ai_engine.build_chapters(transcription.get("segments", []))

        step(92, "Analyzing sentiment timeline...")
        timeline = ai_engine.sentiment_timeline(optimized)

        step(96, "Saving to database...")
        record = {
            "title": title,
            "language": transcription.get("language", language),
            "was_translated": was_translated,
            "raw_transcript": raw_text,
            "translated_text": english_text,
            "optimized_text": optimized,
            "notes": notes,
            "chapters": chapters,
            "sentiment_timeline": timeline,
            "talk_time": transcription.get("talk_time", {}),
            "has_speakers": transcription.get("has_speakers", False),
        }
        meeting_id = database.save_meeting(username, record)

        # We don't keep the raw audio around after processing.
        try:
            os.remove(file_path)
        except OSError:
            pass

        step(100, "Done!")
        final_state = get_job_state(job_id) or {}
        final_state["status"] = "done"
        final_state["meeting_id"] = meeting_id
        update_job_state(job_id, final_state)

    except Exception as exc:
        traceback.print_exc()
        err_state = get_job_state(job_id) or {}
        err_state["status"] = "error"
        err_state["message"] = f"Something went wrong: {exc}"
        update_job_state(job_id, err_state)


# ---- auth ----

@app.route("/api", methods=["GET", "POST"])
@app.route("/api/index", methods=["GET", "POST"])
def api_home():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        # Check if login or register
        if request.form.get("is_register"):
            ok, msg = register_user(username, password)
            flash(msg, "success" if ok else "error")
            if ok:
                return redirect(url_for("login"))
            return render_template("register.html")
        else:
            ok, msg = verify_user(username, password)
            if ok:
                session["username"] = username
                return redirect(url_for("index"))
            flash(msg, "error")
            return render_template("login.html")
    if "username" in session:
        return render_template("index.html", username=session["username"])
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        ok, msg = register_user(request.form.get("username"),
                                request.form.get("password"))
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        ok, msg = verify_user(username, request.form.get("password"))
        if ok:
            session["username"] = username
            return redirect(url_for("index"))
        flash(msg, "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---- main pages ----

@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session["username"])


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    # Takes the file, saves it, and starts the job.
    if "audio" not in request.files:
        return jsonify({"error": "No audio file received."}), 400

    file = request.files["audio"]
    ext = os.path.splitext(file.filename)[1].lower() or ".webm"
    if ext not in ALLOWED:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    filename = secure_filename(f"{os.urandom(6).hex()}{ext}")
    file_path = os.path.join(UPLOAD_DIR, filename)
    file.save(file_path)

    title = request.form.get("title") or "Untitled Meeting"
    language = request.form.get("language", "auto")
    output_language = request.form.get("output_language", "English")

    job_id = os.urandom(8).hex()
    initial_job = {"status": "working", "progress": 5,
                   "message": "Starting...", "meeting_id": None}
    update_job_state(job_id, initial_job)

    # In serverless environments like Vercel (where background threads are paused when response returns),
    # process directly during the request. On persistent servers, use a thread.
    is_serverless = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    if is_serverless:
        process_meeting(job_id, session["username"], file_path, title,
                        language, output_language)
    else:
        thread = threading.Thread(
            target=process_meeting,
            args=(job_id, session["username"], file_path, title,
                  language, output_language),
            daemon=True,
        )
        thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
@login_required
def status(job_id):
    # Polled by the progress bar on the upload page.
    job = get_job_state(job_id)
    if not job:
        return jsonify({"error": "Unknown job."}), 404
    return jsonify(job)


@app.route("/results/<meeting_id>")
@login_required
def results(meeting_id):
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        flash("Meeting not found.", "error")
        return redirect(url_for("history"))
    return render_template("results.html", meeting=meeting,
                           username=session["username"])


@app.route("/history")
@login_required
def history():
    search = request.args.get("q", "").strip()
    meetings = database.list_meetings(session["username"], search or None)
    return render_template("history.html", meetings=meetings,
                           search=search, username=session["username"])


# ---- per-meeting actions (chat, email, tasks, downloads) ----

@app.route("/chat/<meeting_id>", methods=["POST"])
@login_required
def chat(meeting_id):
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found."}), 404

    data = request.get_json(force=True)
    question = data.get("question", "")
    history = data.get("history", [])
    transcript = meeting.get("optimized_text") or meeting.get("raw_transcript", "")

    try:
        answer = ai_engine.chat_with_meeting(transcript, question, history)
        return jsonify({"answer": answer})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/email/<meeting_id>", methods=["POST"])
@login_required
def email_draft(meeting_id):
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found."}), 404
    try:
        draft = ai_engine.draft_followup_email(meeting.get("notes", {}))
        return jsonify({"email": draft})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/action-items/<meeting_id>", methods=["POST"])
@login_required
def save_action_items(meeting_id):
    data = request.get_json(force=True)
    database.update_action_items(session["username"], meeting_id,
                                 data.get("action_items", []))
    return jsonify({"ok": True})


@app.route("/download/<meeting_id>/<file_format>")
@login_required
def download(meeting_id, file_format):
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        flash("Meeting not found.", "error")
        return redirect(url_for("history"))

    title = meeting.get("title", "Meeting")
    notes = meeting.get("notes", {})

    if file_format == "pdf":
        path = exports.make_pdf(title, notes)
    elif file_format == "docx":
        path = exports.make_docx(title, notes)
    else:
        flash("Unknown format.", "error")
        return redirect(url_for("results", meeting_id=meeting_id))

    return send_file(path, as_attachment=True)


@app.route("/translate-notes/<meeting_id>", methods=["POST"])
@login_required
def translate_notes(meeting_id):
    # Re-runs generate_notes in the requested language.
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found."}), 404
    data = request.get_json(force=True)
    language = data.get("language", "English")
    transcript = meeting.get("optimized_text") or meeting.get("raw_transcript", "")
    try:
        notes = ai_engine.generate_notes(transcript, language)
        return jsonify({"notes": notes})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---- the bigger features (dashboard, cross-meeting assistant, audio, etc.) ----

@app.route("/insights")
@login_required
def insights():
    # Roll up a few numbers across all of the user's meetings for the dashboard.
    meetings = database.list_meetings(session["username"])

    total = len(meetings)
    total_actions = done_actions = 0
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    keyword_counts = {}
    timeline = []

    for m in meetings:
        notes = m.get("notes", {})
        items = notes.get("action_items", [])
        total_actions += len(items)
        done_actions += sum(1 for a in items if a.get("done"))

        label = (notes.get("sentiment", {}) or {}).get("label", "Neutral")
        if label in sentiment_counts:
            sentiment_counts[label] += 1

        for kw in notes.get("keywords", []):
            key = str(kw).strip().lower()
            if key:
                keyword_counts[key] = keyword_counts.get(key, 0) + 1

        timeline.append(m.get("created_at", "")[:10])

    top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    day_counts = {}
    for d in timeline:
        if d:
            day_counts[d] = day_counts.get(d, 0) + 1
    trend = sorted(day_counts.items())

    completion = round((done_actions / total_actions) * 100) if total_actions else 0

    return render_template(
        "insights.html", username=session["username"], total=total,
        total_actions=total_actions, done_actions=done_actions,
        completion=completion, sentiment_counts=sentiment_counts,
        top_keywords=top_keywords, trend=trend,
    )


@app.route("/assistant")
@login_required
def assistant():
    return render_template("assistant.html", username=session["username"])


@app.route("/assistant/ask", methods=["POST"])
@login_required
def assistant_ask():
    meetings = database.list_meetings(session["username"])
    question = request.get_json(force=True).get("question", "")
    try:
        answer = ai_engine.ask_across_meetings(meetings, question)
        return jsonify({"answer": answer})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/listen/<meeting_id>")
@login_required
def listen(meeting_id):
    # Turns the summary (+ decisions) into an mp3 and streams it back.
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found."}), 404

    notes = meeting.get("notes", {})
    script = "Meeting summary. " + notes.get("summary", "")
    decisions = notes.get("decisions", [])
    if decisions:
        script += " Key decisions: " + ". ".join(decisions)

    out_path = os.path.join(exports.EXPORT_DIR, f"{meeting_id}.mp3")
    try:
        ai_engine.text_to_speech(script, out_path)
        return send_file(out_path, mimetype="audio/mpeg")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/calendar/<meeting_id>")
@login_required
def calendar(meeting_id):
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        flash("Meeting not found.", "error")
        return redirect(url_for("history"))
    path = exports.make_ics(meeting.get("title", "Meeting"),
                            meeting.get("notes", {}).get("action_items", []))
    return send_file(path, as_attachment=True)


@app.route("/send-email/<meeting_id>", methods=["POST"])
@login_required
def send_email(meeting_id):
    # Sends the follow-up over SMTP when it's configured; otherwise it just
    # returns the drafted text so the user can copy/paste it themselves.
    meeting = database.get_meeting(session["username"], meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found."}), 404

    recipients = request.get_json(force=True).get("to", "").strip()
    try:
        body = ai_engine.draft_followup_email(meeting.get("notes", {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()

    if not (host and user and password and recipients):
        return jsonify({"sent": False, "draft": body,
                        "note": "SMTP not configured — here is the draft to send manually."})

    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = "Meeting Follow-up: " + meeting.get("title", "")
        msg["From"] = user
        msg["To"] = recipients
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [r.strip() for r in recipients.split(",")], msg.as_string())
        return jsonify({"sent": True})
    except Exception as exc:
        return jsonify({"sent": False, "draft": body, "note": f"Send failed: {exc}"})


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    import traceback
    tb = traceback.format_exc()
    print("=== UNHANDLED FLASK EXCEPTION ===", flush=True)
    print(tb, flush=True)
    if request.is_json or request.path.startswith("/chat") or request.path.startswith("/upload"):
        return jsonify({"error": str(e), "traceback": tb}), 500
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Application Error</title>
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; }}
            .card {{ max-width: 800px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 28px; border: 1px solid #334155; }}
            h1 {{ color: #f87171; font-size: 24px; margin-top: 0; }}
            pre {{ background: #090d16; padding: 16px; border-radius: 8px; overflow-x: auto; color: #38bdf8; font-size: 13px; line-height: 1.5; }}
            a {{ color: #60a5fa; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⚠️ Application Error</h1>
            <p><b>Exception:</b> {type(e).__name__}: {str(e)}</p>
            <pre>{tb}</pre>
            <p><a href="/login">← Back to Login</a></p>
        </div>
    </body>
    </html>
    """, 500


if __name__ == "__main__":
    # use_reloader=False because the auto-reloader watches every installed
    # package and restarts in a loop on some setups. Debug pages stay on.
    app.run(debug=True, use_reloader=False, host="127.0.0.1", port=5000)

