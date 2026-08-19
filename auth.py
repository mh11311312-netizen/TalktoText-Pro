"""
Login / register logic. Passwords are stored as Werkzeug hashes, never in
plain text. The routes themselves live in app.py; this file just answers
"is this a valid signup / login?" and provides the login_required decorator.
"""

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
    if not database.create_user(username, password_hash):
        return False, "That username is already taken."
    return True, "Account created! Please log in."


def verify_user(username, password):
    user = database.get_user((username or "").strip())
    if not user:
        return False, "No account found with that username."
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
