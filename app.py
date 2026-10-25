import os
import random
import re
import string
import threading
import time
from dataclasses import dataclass, field

from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-for-production")
socketio = SocketIO(app, cors_allowed_origins=[], async_mode="threading")

MAX_PLAYERS = 8
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
rooms = {}
rooms_lock = threading.RLock()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"ok": True}


def clean_name(value):
    value = re.sub(r"[<>]", "", str(value or "")).strip()
    return value[:16] or "Player"


def make_code():
    with rooms_lock:
        while True:
            code = "".join(random.choice(CODE_ALPHABET) for _ in range(5))
            if code not in rooms:
                return code


def public_room(room):
    return {
        "code": room["code"],
        "host_sid": room["host_sid"],
        "status": room["status"],
        "game": room["game"],
        "players": [
            {"sid": sid, "name": player["name"], "is_host": sid == room["host_sid"]}
            for sid, player in room["players"].items()
        ],
    }


def send_room(room):
    socketio.emit("room:update", public_room(room), to=room["code"])


def clear_round_timer(room):
    timer = room.get("timer")
    if timer:
        timer.cancel()
    room["timer"] = None


def leave_current_room(sid):
    with rooms_lock:
        code = next((code for code, room in rooms.items() if sid in room["players"]), None)
        if not code:
            return
        room = rooms[code]
        room["players"].pop(sid, None)
        leave_room(code, sid=sid)

        if not room["players"]:
            clear_round_timer(room)
            rooms.pop(code, None)
            return

        if room["host_sid"] == sid:
            room["host_sid"] = next(iter(room["players"]))

        if room["status"] == "playing":
            clear_round_timer(room)
            room["status"] = "lobby"
            room["round"] = None
            socketio.emit("game:state", {"phase": "lobby", "message": "A player left. Back in the lobby."}, to=code)
        send_room(room)


def room_for_sid(sid):
    with rooms_lock:
        for room in rooms.values():
            if sid in room["players"]:
                return room
    return None


def send_scores(room):
    round_state = room["round"]
    results = [
        {"sid": sid, "name": room["players"].get(sid, {}).get("name", "Player"), "reaction_ms": ms}
        for sid, ms in round_state["results"].items()
    ]
    false_starts = [
        {"sid": sid, "name": room["players"].get(sid, {}).get("name", "Player")}
        for sid in round_state["false_starts"]
        if sid in room["players"]
    ]
    results.sort(key=lambda item: item["reaction_ms"])
    socketio.emit("game:scores", {"results": results, "false_starts": false_starts}, to=room["code"])


def begin_go_phase(code, round_number):
    with rooms_lock:
        room = rooms.get(code)
        if not room or room["status"] != "playing" or not room.get("round"):
            return
        if room["round"]["number"] != round_number or room["round"]["phase"] != "waiting":
            return
        room["round"]["phase"] = "go"
        room["round"]["started_at"] = time.monotonic()
        room["timer"] = None
        message = {
            "phase": "go",
            "round_number": round_number,
            "message": "CLICK NOW!",
        }
    socketio.emit("game:state", message, to=code)


def start_round(room, number):
    clear_round_timer(room)
    room["round"] = {
        "number": number,
        "phase": "waiting",
        "started_at": None,
        "false_starts": set(),
        "results": {},
    }
    socketio.emit("game:state", {
        "phase": "waiting",
        "round_number": number,
        "message": "Get ready… wait for the green signal!",
    }, to=room["code"])
    timer = threading.Timer(random.uniform(1.8, 5.0), begin_go_phase, args=(room["code"], number))
    timer.daemon = True
    room["timer"] = timer
    timer.start()


@socketio.on("connect")
def on_connect():
    emit("server:ready", {"message": "Connected to Lunchbox Arcade."})


@socketio.on("room:create")
def on_room_create(payload):
    leave_current_room(request_sid())
    sid = request_sid()
    room = {
        "code": make_code(),
        "host_sid": sid,
        "status": "lobby",
        "game": "reaction-race",
        "players": {sid: {"name": clean_name((payload or {}).get("name"))}},
        "round": None,
        "timer": None,
    }
    with rooms_lock:
        rooms[room["code"]] = room
    join_room(room["code"])
    emit("room:joined", public_room(room))
    send_room(room)


@socketio.on("room:join")
def on_room_join(payload):
    sid = request_sid()
    payload = payload or {}
    code = str(payload.get("code", "")).strip().upper()
    with rooms_lock:
        room = rooms.get(code)
        if not room:
            emit("app:error", "That room code doesn't exist.")
            return
        if room["status"] == "playing":
            emit("app:error", "That game has already started.")
            return
        if len(room["players"]) >= MAX_PLAYERS:
            emit("app:error", "That room is full (8 players maximum).")
            return

    leave_current_room(sid)
    with rooms_lock:
        # Check again after leaving any previous room.
        room = rooms.get(code)
        if not room or room["status"] != "lobby":
            emit("app:error", "That room is no longer available.")
            return
        if len(room["players"]) >= MAX_PLAYERS:
            emit("app:error", "That room is full (8 players maximum).")
            return
        room["players"][sid] = {"name": clean_name(payload.get("name"))}
    join_room(code)
    emit("room:joined", public_room(room))
    send_room(room)


@socketio.on("room:leave")
def on_room_leave():
    leave_current_room(request_sid())


@socketio.on("game:start")
def on_game_start():
    sid = request_sid()
    with rooms_lock:
        room = next((r for r in rooms.values() if sid in r["players"]), None)
        if not room:
            emit("app:error", "Join a room first.")
            return
        if room["host_sid"] != sid:
            emit("app:error", "Only the host can start the game.")
            return
        if len(room["players"]) < 2:
            emit("app:error", "You need at least 2 players to start.")
            return
        if room["status"] == "playing":
            return
        room["status"] = "playing"
        start_round(room, 1)
        send_room(room)


@socketio.on("game:react")
def on_game_react():
    sid = request_sid()
    with rooms_lock:
        room = next((r for r in rooms.values() if sid in r["players"]), None)
        if not room or room["status"] != "playing" or not room.get("round"):
            return
        round_state = room["round"]
        if round_state["phase"] == "waiting":
            round_state["false_starts"].add(sid)
            emit("game:feedback", {"type": "early", "message": "Too early! Wait for green."})
            send_scores(room)
            return
        if round_state["phase"] != "go" or sid in round_state["results"]:
            return
        reaction_ms = max(0, round((time.monotonic() - round_state["started_at"]) * 1000))
        round_state["results"][sid] = reaction_ms
        emit("game:feedback", {"type": "result", "reaction_ms": reaction_ms})
        all_done = all(
            player_sid in round_state["results"] or player_sid in round_state["false_starts"]
            for player_sid in room["players"]
        )
        send_scores(room)
        if all_done:
            round_state["phase"] = "results"
            clear_round_timer(room)
            socketio.emit("game:state", {
                "phase": "results",
                "round_number": round_state["number"],
                "message": "Round over!",
            }, to=room["code"])


@socketio.on("game:next")
def on_game_next():
    sid = request_sid()
    with rooms_lock:
        room = next((r for r in rooms.values() if sid in r["players"]), None)
        if not room or room["host_sid"] != sid or room["status"] != "playing" or not room.get("round"):
            return
        if room["round"]["phase"] != "results":
            emit("app:error", "Finish the current round first.")
            return
        start_round(room, room["round"]["number"] + 1)


@socketio.on("game:back-to-lobby")
def on_back_to_lobby():
    sid = request_sid()
    with rooms_lock:
        room = next((r for r in rooms.values() if sid in r["players"]), None)
        if not room or room["host_sid"] != sid:
            return
        clear_round_timer(room)
        room["status"] = "lobby"
        room["round"] = None
        send_room(room)
    socketio.emit("game:state", {"phase": "lobby", "message": "Back in the lobby."}, to=room["code"])


@socketio.on("disconnect")
def on_disconnect():
    leave_current_room(request_sid())


# Flask-SocketIO exposes the active request through flask.request.
from flask import request

def request_sid():
    return request.sid


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False)
