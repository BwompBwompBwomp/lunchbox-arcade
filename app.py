import math
import os
import random
import re
import threading
import time

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-for-production")
socketio = SocketIO(app, cors_allowed_origins=[], async_mode="threading")

MAX_PLAYERS = 8
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_GAMES = {"reaction-race", "knockout"}
rooms = {}
rooms_lock = threading.RLock()

ARENA_WIDTH = 700
ARENA_HEIGHT = 420
KNOCKOUT_START_RADIUS = 174
KNOCKOUT_MIN_RADIUS = 78
KNOCKOUT_SHRINK_PER_SECOND = 1.8
KNOCKOUT_ROUND_SECONDS = 55
PLAYER_SPEED = 180
PLAYER_RADIUS = 13
PLAYER_COLORS = ["#a18aff", "#79f2c0", "#ff87bd", "#ffc66d", "#75c9ff", "#ff806e", "#d2f36b", "#e8a4ff"]


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
        if room.get("knockout"):
            room["knockout"]["players"].pop(sid, None)
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
            room["knockout"] = None
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
        if room["game"] != "reaction-race" or room["round"]["number"] != round_number or room["round"]["phase"] != "waiting":
            return
        room["round"]["phase"] = "go"
        room["round"]["started_at"] = time.monotonic()
        room["timer"] = None
    socketio.emit("game:state", {"phase": "go", "round_number": round_number, "message": "Click now!"}, to=code)


def start_reaction_round(room, number):
    clear_round_timer(room)
    room["knockout"] = None
    room["round"] = {"number": number, "phase": "waiting", "started_at": None, "false_starts": set(), "results": {}}
    socketio.emit("game:state", {
        "phase": "waiting", "game": "reaction-race", "round_number": number,
        "message": "Wait for the green signal, then click."
    }, to=room["code"])
    timer = threading.Timer(random.uniform(1.8, 5.0), begin_go_phase, args=(room["code"], number))
    timer.daemon = True
    room["timer"] = timer
    timer.start()


def start_knockout_round(room, number=1):
    clear_round_timer(room)
    room["round"] = {"number": number, "phase": "playing"}
    players = {}
    count = max(1, len(room["players"]))
    center_x, center_y = ARENA_WIDTH / 2, ARENA_HEIGHT / 2
    spawn_radius = min(105, 28 * count)
    for index, sid in enumerate(room["players"]):
        angle = (2 * math.pi * index / count) - math.pi / 2
        players[sid] = {
            "x": center_x + math.cos(angle) * spawn_radius,
            "y": center_y + math.sin(angle) * spawn_radius,
            "vx": 0.0,
            "vy": 0.0,
            "input": {"up": False, "down": False, "left": False, "right": False},
            "alive": True,
            "color": PLAYER_COLORS[index % len(PLAYER_COLORS)],
        }
    room["knockout"] = {
        "number": number,
        "phase": "playing",
        "started_at": time.monotonic(),
        "radius": KNOCKOUT_START_RADIUS,
        "players": players,
        "winner_sid": None,
    }
    socketio.emit("game:state", {"phase": "knockout", "game": "knockout", "round_number": number}, to=room["code"])
    send_knockout_state(room)


def send_knockout_state(room):
    state = room.get("knockout")
    if not state:
        return
    player_rows = []
    for sid, player in state["players"].items():
        details = room["players"].get(sid)
        if not details:
            continue
        player_rows.append({
            "sid": sid,
            "name": details["name"],
            "x": round(player["x"], 1),
            "y": round(player["y"], 1),
            "alive": player["alive"],
            "color": player["color"],
        })
    winner = room["players"].get(state.get("winner_sid"), {}).get("name") if state.get("winner_sid") else None
    elapsed = time.monotonic() - state["started_at"]
    socketio.emit("knockout:state", {
        "phase": state["phase"],
        "radius": round(state["radius"], 1),
        "players": player_rows,
        "seconds_left": max(0, math.ceil(KNOCKOUT_ROUND_SECONDS - elapsed)),
        "winner": winner,
        "round_number": state["number"],
    }, to=room["code"])


def knockout_tick():
    previous = time.monotonic()
    while True:
        socketio.sleep(0.05)
        now = time.monotonic()
        dt = min(0.08, now - previous)
        previous = now
        with rooms_lock:
            active_rooms = list(rooms.values())
            for room in active_rooms:
                state = room.get("knockout")
                if room["status"] != "playing" or room["game"] != "knockout" or not state or state["phase"] != "playing":
                    continue
                elapsed = now - state["started_at"]
                state["radius"] = max(KNOCKOUT_MIN_RADIUS, KNOCKOUT_START_RADIUS - elapsed * KNOCKOUT_SHRINK_PER_SECOND)
                player_ids = list(state["players"].keys())
                for sid in player_ids:
                    player = state["players"].get(sid)
                    if not player or not player["alive"]:
                        continue
                    controls = player["input"]
                    dx = float(controls["right"]) - float(controls["left"])
                    dy = float(controls["down"]) - float(controls["up"])
                    magnitude = math.hypot(dx, dy)
                    if magnitude:
                        dx, dy = dx / magnitude, dy / magnitude
                        player["vx"] = dx * PLAYER_SPEED
                        player["vy"] = dy * PLAYER_SPEED
                    else:
                        player["vx"] *= 0.78
                        player["vy"] *= 0.78
                    player["x"] = max(PLAYER_RADIUS, min(ARENA_WIDTH - PLAYER_RADIUS, player["x"] + player["vx"] * dt))
                    player["y"] = max(PLAYER_RADIUS, min(ARENA_HEIGHT - PLAYER_RADIUS, player["y"] + player["vy"] * dt))

                # Players bump into each other and push each other away.
                for i, sid_a in enumerate(player_ids):
                    a = state["players"].get(sid_a)
                    if not a or not a["alive"]:
                        continue
                    for sid_b in player_ids[i + 1:]:
                        b = state["players"].get(sid_b)
                        if not b or not b["alive"]:
                            continue
                        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                        distance = math.hypot(dx, dy)
                        minimum = PLAYER_RADIUS * 2
                        if distance < minimum:
                            if distance < 0.01:
                                dx, dy, distance = 1.0, 0.0, 1.0
                            nx, ny = dx / distance, dy / distance
                            overlap = (minimum - distance) / 2
                            a["x"] -= nx * overlap
                            a["y"] -= ny * overlap
                            b["x"] += nx * overlap
                            b["y"] += ny * overlap
                            a["vx"] -= nx * 72
                            a["vy"] -= ny * 72
                            b["vx"] += nx * 72
                            b["vy"] += ny * 72

                center_x, center_y = ARENA_WIDTH / 2, ARENA_HEIGHT / 2
                for player in state["players"].values():
                    if not player["alive"]:
                        continue
                    distance_from_center = math.hypot(player["x"] - center_x, player["y"] - center_y)
                    if distance_from_center > state["radius"]:
                        player["alive"] = False

                alive_ids = [sid for sid, player in state["players"].items() if player["alive"]]
                if len(alive_ids) <= 1 or elapsed >= KNOCKOUT_ROUND_SECONDS:
                    state["phase"] = "results"
                    state["winner_sid"] = alive_ids[0] if len(alive_ids) == 1 else None
                    room["round"]["phase"] = "results"
                send_knockout_state(room)


@socketio.on("connect")
def on_connect():
    emit("server:ready", {"message": "Connected."})


@socketio.on("room:create")
def on_room_create(payload):
    sid = request.sid
    leave_current_room(sid)
    payload = payload or {}
    room = {
        "code": make_code(),
        "host_sid": sid,
        "status": "lobby",
        "game": "reaction-race",
        "players": {sid: {"name": clean_name(payload.get("name"))}},
        "round": None,
        "knockout": None,
        "timer": None,
    }
    with rooms_lock:
        rooms[room["code"]] = room
    join_room(room["code"])
    emit("room:joined", public_room(room))
    send_room(room)


@socketio.on("room:join")
def on_room_join(payload):
    sid = request.sid
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
    leave_current_room(request.sid)


@socketio.on("game:select")
def on_game_select(payload):
    sid = request.sid
    game = str((payload or {}).get("game", ""))
    with rooms_lock:
        room = room_for_sid(sid)
        if not room or room["status"] != "lobby":
            return
        if room["host_sid"] != sid:
            emit("app:error", "Only the host can choose the game.")
            return
        if game not in ROOM_GAMES:
            emit("app:error", "That game isn't available yet.")
            return
        room["game"] = game
        send_room(room)


@socketio.on("game:start")
def on_game_start():
    sid = request.sid
    with rooms_lock:
        room = room_for_sid(sid)
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
        if room["game"] == "knockout":
            start_knockout_round(room, 1)
        else:
            start_reaction_round(room, 1)
        send_room(room)


@socketio.on("game:react")
def on_game_react():
    sid = request.sid
    with rooms_lock:
        room = room_for_sid(sid)
        if not room or room["status"] != "playing" or room["game"] != "reaction-race" or not room.get("round"):
            return
        round_state = room["round"]
        if sid in round_state["false_starts"]:
            return
        if round_state["phase"] == "waiting":
            round_state["false_starts"].add(sid)
            emit("game:feedback", {"type": "early", "message": "Too early. Wait for green."})
            send_scores(room)
            return
        if round_state["phase"] != "go" or sid in round_state["results"]:
            return
        reaction_ms = max(0, round((time.monotonic() - round_state["started_at"]) * 1000))
        round_state["results"][sid] = reaction_ms
        emit("game:feedback", {"type": "result", "reaction_ms": reaction_ms})
        all_done = all(player_sid in round_state["results"] or player_sid in round_state["false_starts"] for player_sid in room["players"])
        send_scores(room)
        if all_done:
            round_state["phase"] = "results"
            clear_round_timer(room)
            socketio.emit("game:state", {"phase": "results", "game": "reaction-race", "round_number": round_state["number"], "message": "Round over."}, to=room["code"])


@socketio.on("knockout:input")
def on_knockout_input(payload):
    sid = request.sid
    payload = payload or {}
    with rooms_lock:
        room = room_for_sid(sid)
        if not room or room["status"] != "playing" or room["game"] != "knockout":
            return
        state = room.get("knockout")
        player = state and state["players"].get(sid)
        if not player or not player["alive"] or state["phase"] != "playing":
            return
        player["input"] = {key: bool(payload.get(key, False)) for key in ("up", "down", "left", "right")}


@socketio.on("game:next")
def on_game_next():
    sid = request.sid
    with rooms_lock:
        room = room_for_sid(sid)
        if not room or room["host_sid"] != sid or room["status"] != "playing" or not room.get("round"):
            return
        if room["round"]["phase"] != "results":
            emit("app:error", "Finish the current round first.")
            return
        number = room["round"]["number"] + 1
        if room["game"] == "knockout":
            start_knockout_round(room, number)
        else:
            start_reaction_round(room, number)


@socketio.on("game:back-to-lobby")
def on_back_to_lobby():
    sid = request.sid
    with rooms_lock:
        room = room_for_sid(sid)
        if not room or room["host_sid"] != sid:
            return
        clear_round_timer(room)
        room["status"] = "lobby"
        room["round"] = None
        room["knockout"] = None
        send_room(room)
    socketio.emit("game:state", {"phase": "lobby", "message": "Back in the lobby."}, to=room["code"])


@socketio.on("disconnect")
def on_disconnect():
    leave_current_room(request.sid)


socketio.start_background_task(knockout_tick)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False)
