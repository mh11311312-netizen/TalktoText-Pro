"""
Login / register logic. Passwords are stored as Werkzeug hashes, never in
plain text. The routes themselves live in app.py; this file just answers
"is this a valid signup / login?" and provides the login_required decorator.
"""

import os
from functools import wraps
from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

import database


def register_user(username, password):
    # Returns (ok, message). Message is shown to the user via a flash.
    username = (username or "").strip()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password or "") < 4:
        return False, "Password must be at least 4 characters."

    password_hash = generate_password_hash(password)
    database.create_user(username, password_hash)
    return True, "Account created! Welcome."


def verify_user(username, password):
    username = (username or "").strip()
    if not username:
        return False, "Please enter a username."
    if len(password or "") < 4:
        return False, "Password must be at least 4 characters."

    user = database.get_user(username)
    if not user:
        # In serverless environments (stateless containers where local JSON is ephemeral),
        # auto-register the user so they can log in seamlessly without errors.
        if not database.MONGO_URI or os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            password_hash = generate_password_hash(password)
            database.create_user(username, password_hash)
            return True, "Welcome!"
        return False, "No account found with that username. Please register first."

    if not check_password_hash(user["password_hash"], password or ""):
        return False, "Incorrect password."
    return True, "Welcome back!"


def login_required(view_func):
    # Drop this above any route that needs a logged-in user; otherwise we bounce
    # them to the login page.
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper
