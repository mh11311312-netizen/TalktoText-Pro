"""
Data access layer. We use MongoDB as the main store, but I added a small
JSON-file fallback so the app still runs on a machine that doesn't have Mongo
set up yet. Everything else in the app just calls these functions and doesn't
care which mode is active.
"""

import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "talktotext")
JSON_PATH = os.path.join(os.path.dirname(__file__), "data_store.json")

_mode = None          # set to "mongo" or "json" once we've connected
_users = None
_meetings = None


def _connect():
    # Lazy connect on first use. Tries Mongo, falls back to the JSON file.
    global _mode, _users, _meetings
    if _mode is not None:
        return

    if MONGO_URI:
        try:
            from pymongo import MongoClient
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
            client.admin.command("ping")          # fails fast if unreachable
            db = client[MONGO_DB]
            _users = db["users"]
            _meetings = db["meetings"]
            _mode = "mongo"
            print("[database] Connected to MongoDB.")
            return
        except Exception as exc:
            print(f"[database] MongoDB unavailable ({exc}). Using local JSON file.")

    _mode = "json"
    if not os.path.exists(JSON_PATH):
        with open(JSON_PATH, "w") as f:
            json.dump({"users": [], "meetings": []}, f)
    print("[database] Using local JSON storage (data_store.json).")


def _read_json():
    with open(JSON_PATH, "r") as f:
        return json.load(f)


def _write_json(data):
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ---- users ----

def create_user(username, password_hash):
    # Returns False if the username is taken.
    _connect()
    if _mode == "mongo":
        if _users.find_one({"username": username}):
            return False
        _users.insert_one({"username": username, "password_hash": password_hash})
        return True
    else:
        data = _read_json()
        if any(u["username"] == username for u in data["users"]):
            return False
        data["users"].append({"username": username, "password_hash": password_hash})
        _write_json(data)
        return True


def get_user(username):
    _connect()
    if _mode == "mongo":
        return _users.find_one({"username": username})
    data = _read_json()
    for u in data["users"]:
        if u["username"] == username:
            return u
    return None


# ---- meetings ----

def save_meeting(username, record):
    # 'record' already holds the transcript, notes, chapters, etc. We just tag
    # it with an id, the owner, and a timestamp, then store it.
    _connect()
    meeting_id = uuid.uuid4().hex
    record["_id"] = meeting_id
    record["username"] = username
    record["created_at"] = datetime.utcnow().isoformat()

    if _mode == "mongo":
        _meetings.insert_one(record)
    else:
        data = _read_json()
        data["meetings"].append(record)
        _write_json(data)
    return meeting_id


def get_meeting(username, meeting_id):
    # Scoped to the owner so users can't open each other's meetings.
    _connect()
    if _mode == "mongo":
        return _meetings.find_one({"_id": meeting_id, "username": username})
    data = _read_json()
    for m in data["meetings"]:
        if m["_id"] == meeting_id and m["username"] == username:
            return m
    return None


def list_meetings(username, search=None):
    # Newest first. If a search term is passed we do a simple contains-match
    # over the whole record and attach a little snippet of where it hit.
    _connect()
    if _mode == "mongo":
        results = list(_meetings.find({"username": username}))
    else:
        data = _read_json()
        results = [m for m in data["meetings"] if m["username"] == username]

    results.sort(key=lambda m: m.get("created_at", ""), reverse=True)

    if search:
        term = search.lower()
        filtered = []
        for m in results:
            haystack = json.dumps(m, default=str).lower()
            if term in haystack:
                idx = haystack.find(term)
                m["_snippet"] = "..." + haystack[max(0, idx - 40): idx + 60] + "..."
                filtered.append(m)
        return filtered

    return results


def update_action_items(username, meeting_id, action_items):
    # Persists the checkbox (done/not-done) state for a meeting's tasks.
    _connect()
    if _mode == "mongo":
        _meetings.update_one(
            {"_id": meeting_id, "username": username},
            {"$set": {"notes.action_items": action_items}},
        )
    else:
        data = _read_json()
        for m in data["meetings"]:
            if m["_id"] == meeting_id and m["username"] == username:
                m["notes"]["action_items"] = action_items
        _write_json(data)
