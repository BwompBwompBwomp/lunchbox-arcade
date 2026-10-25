const socket = io();
const $ = id => document.getElementById(id);
const setup = $("setup");
const roomPanel = $("roomPanel");
const gamePanel = $("gamePanel");
const knockoutPanel = $("knockoutPanel");
const playerName = $("playerName");
const roomCodeInput = $("roomCode");
const createBtn = $("createBtn");
const joinBtn = $("joinBtn");
const startBtn = $("startBtn");
const leaveBtn = $("leaveBtn");
const copyCodeBtn = $("copyCodeBtn");
const reactionPad = $("reactionPad");
const reactionMessage = $("reactionMessage");
const reactionSub = $("reactionSub");
const reactionEmoji = $("reactionEmoji");
const feedback = $("feedback");
const scoresList = $("scoresList");
const nextBtn = $("nextBtn");
const backBtn = $("backBtn");
const knockoutCanvas = $("knockoutCanvas");
const knockoutContext = knockoutCanvas.getContext("2d");
const knockoutAgainBtn = $("knockoutAgainBtn");
const knockoutBackBtn = $("knockoutBackBtn");

let currentRoom = null;
let mySocketId = null;
let gamePhase = "lobby";
let toastTimeout;
let knockoutState = null;
const controls = { up: false, down: false, left: false, right: false };
const keyMap = { ArrowUp: "up", KeyW: "up", ArrowDown: "down", KeyS: "down", ArrowLeft: "left", KeyA: "left", ArrowRight: "right", KeyD: "right" };

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.add("hidden"), 2800);
}
function nameValue() {
  const value = playerName.value.trim().slice(0, 16);
  if (!value) { playerName.focus(); showToast("Enter your name first."); return null; }
  return value;
}
function chosenGameName(game) { return game === "knockout" ? "Knockout" : "Reaction Race"; }
function showRoom(room) {
  currentRoom = room;
  setup.classList.add("hidden");
  roomPanel.classList.remove("hidden");
  $("roomCodeDisplay").textContent = room.code;
  $("roomStatus").textContent = room.status === "playing" ? "Game in progress" : `${room.players.length}/8 players`;
  $("playersList").replaceChildren();
  room.players.forEach(player => {
    const card = document.createElement("div");
    card.className = "player";
    const name = document.createElement("div");
    name.className = "player-name";
    name.textContent = player.name;
    const role = document.createElement("div");
    role.className = "player-role";
    role.textContent = player.is_host ? "HOST" : "PLAYER";
    card.append(name, role);
    $("playersList").append(card);
  });
  const isHost = room.host_sid === mySocketId;
  document.querySelectorAll("[data-game]").forEach(button => {
    button.classList.toggle("selected", button.dataset.game === room.game);
    button.disabled = !isHost || room.status === "playing";
  });
  $("gameChoiceHint").textContent = room.game === "knockout"
    ? "Move around and push the other players off."
    : "Click when the screen turns green.";
  startBtn.disabled = !isHost || room.players.length < 2 || room.status === "playing";
  startBtn.textContent = room.status === "playing" ? "Game in progress" : `Start ${chosenGameName(room.game)}`;
  startBtn.classList.toggle("hidden", room.status === "playing");
  if (room.status !== "playing" && gamePhase === "lobby") {
    gamePanel.classList.add("hidden");
    knockoutPanel.classList.add("hidden");
  }
  if (room.status === "playing" && room.game === "knockout") {
    gamePanel.classList.add("hidden");
    knockoutPanel.classList.remove("hidden");
  } else if (room.status === "playing") {
    knockoutPanel.classList.add("hidden");
    gamePanel.classList.remove("hidden");
  }
}
function resetGameView() {
  gamePhase = "lobby";
  knockoutState = null;
  gamePanel.classList.add("hidden");
  knockoutPanel.classList.add("hidden");
  nextBtn.classList.add("hidden");
  backBtn.classList.add("hidden");
  knockoutAgainBtn.classList.add("hidden");
  knockoutBackBtn.classList.add("hidden");
  feedback.textContent = "";
  scoresList.innerHTML = '<p class="muted">Results will appear here.</p>';
  resetControls();
}
function selectGame(game) {
  if (currentRoom && currentRoom.host_sid !== mySocketId) return showToast("Only the host can choose the game.");
  socket.emit("game:select", { game });
}
createBtn.addEventListener("click", () => {
  const name = nameValue();
  if (name) socket.emit("room:create", { name });
});
joinBtn.addEventListener("click", () => {
  const name = nameValue();
  const code = roomCodeInput.value.trim().toUpperCase();
  if (!name) return;
  if (!code) return showToast("Enter a room code.");
  socket.emit("room:join", { name, code });
});
roomCodeInput.addEventListener("input", () => { roomCodeInput.value = roomCodeInput.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 5); });
roomCodeInput.addEventListener("keydown", event => { if (event.key === "Enter") joinBtn.click(); });
playerName.addEventListener("keydown", event => { if (event.key === "Enter") createBtn.click(); });
startBtn.addEventListener("click", () => socket.emit("game:start"));
leaveBtn.addEventListener("click", () => {
  socket.emit("room:leave");
  currentRoom = null;
  resetGameView();
  roomPanel.classList.add("hidden");
  setup.classList.remove("hidden");
});
copyCodeBtn.addEventListener("click", async () => {
  if (!currentRoom) return;
  try { await navigator.clipboard.writeText(currentRoom.code); showToast("Room code copied."); }
  catch { showToast(`Room code: ${currentRoom.code}`); }
});
reactionPad.addEventListener("click", () => { if (gamePhase === "waiting" || gamePhase === "go") socket.emit("game:react"); });
nextBtn.addEventListener("click", () => socket.emit("game:next"));
backBtn.addEventListener("click", () => { socket.emit("game:back-to-lobby"); resetGameView(); });
knockoutAgainBtn.addEventListener("click", () => socket.emit("game:next"));
knockoutBackBtn.addEventListener("click", () => { socket.emit("game:back-to-lobby"); resetGameView(); });
document.querySelectorAll("[data-game]").forEach(button => button.addEventListener("click", () => selectGame(button.dataset.game)));

function setControl(direction, pressed) {
  if (!(direction in controls) || controls[direction] === pressed) return;
  controls[direction] = pressed;
  socket.emit("knockout:input", controls);
}
function resetControls() {
  Object.keys(controls).forEach(key => { controls[key] = false; });
  socket.emit("knockout:input", controls);
}
window.addEventListener("keydown", event => {
  const direction = keyMap[event.code];
  if (!direction || gamePhase !== "knockout") return;
  event.preventDefault();
  setControl(direction, true);
});
window.addEventListener("keyup", event => {
  const direction = keyMap[event.code];
  if (direction) setControl(direction, false);
});
window.addEventListener("blur", resetControls);
document.querySelectorAll("[data-dir]").forEach(button => {
  const direction = button.dataset.dir;
  const down = event => { event.preventDefault(); setControl(direction, true); };
  const up = event => { event.preventDefault(); setControl(direction, false); };
  button.addEventListener("pointerdown", down);
  button.addEventListener("pointerup", up);
  button.addEventListener("pointercancel", up);
  button.addEventListener("pointerleave", up);
});

function drawKnockout(state) {
  if (!state) return;
  const ctx = knockoutContext;
  const width = knockoutCanvas.width;
  const height = knockoutCanvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#11111d";
  ctx.fillRect(0, 0, width, height);
  ctx.save();
  ctx.beginPath();
  ctx.arc(width / 2, height / 2, state.radius, 0, Math.PI * 2);
  ctx.fillStyle = "#263b38";
  ctx.fill();
  ctx.lineWidth = 5;
  ctx.strokeStyle = "#79f2c0";
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(width / 2, height / 2, Math.max(0, state.radius - 12), 0, Math.PI * 2);
  ctx.strokeStyle = "#79f2c022";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();
  state.players.forEach(player => {
    ctx.globalAlpha = player.alive ? 1 : 0.28;
    ctx.beginPath();
    ctx.arc(player.x, player.y, 13, 0, Math.PI * 2);
    ctx.fillStyle = player.color;
    ctx.fill();
    ctx.lineWidth = player.sid === mySocketId ? 3 : 1.5;
    ctx.strokeStyle = player.sid === mySocketId ? "#ffffff" : "#151522";
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.font = "600 12px DM Sans, sans-serif";
    ctx.textAlign = "center";
    ctx.fillStyle = player.alive ? "#ffffff" : "#b4b4c3";
    ctx.fillText(player.name, player.x, player.y - 20);
    if (!player.alive) {
      ctx.font = "11px DM Sans, sans-serif";
      ctx.fillText("OUT", player.x, player.y + 27);
    }
  });
}

socket.on("connect", () => { mySocketId = socket.id; });
socket.on("room:joined", room => { showRoom(room); showToast(`Room code: ${room.code}`); });
socket.on("room:update", room => {
  showRoom(room);
  if (room.status === "lobby" && gamePhase !== "lobby") resetGameView();
});
socket.on("app:error", message => showToast(message));
socket.on("game:state", state => {
  gamePhase = state.phase;
  if (state.phase === "lobby") {
    resetGameView();
    return;
  }
  if (state.phase === "knockout") {
    gamePanel.classList.add("hidden");
    knockoutPanel.classList.remove("hidden");
    knockoutAgainBtn.classList.add("hidden");
    knockoutBackBtn.classList.add("hidden");
    $("knockoutMessage").textContent = "Move around and push the other players out.";
    return;
  }
  knockoutPanel.classList.add("hidden");
  gamePanel.classList.remove("hidden");
  $("roundLabel").textContent = state.round_number ? `Round ${state.round_number}` : "";
  reactionPad.className = "reaction-pad";
  feedback.textContent = "";
  if (state.phase === "waiting") {
    reactionPad.classList.add("waiting");
    reactionEmoji.textContent = "⏱️";
    reactionMessage.textContent = "Get ready";
    reactionSub.textContent = "Wait for green, then click.";
    nextBtn.classList.add("hidden"); backBtn.classList.add("hidden");
    scoresList.innerHTML = '<p class="muted">Waiting for everyone to finish.</p>';
  } else if (state.phase === "go") {
    reactionPad.classList.add("go");
    reactionEmoji.textContent = "⚡";
    reactionMessage.textContent = "CLICK NOW";
    reactionSub.textContent = "Click this panel as quickly as you can.";
  } else if (state.phase === "results") {
    reactionPad.classList.add("results");
    reactionEmoji.textContent = "🏁";
    reactionMessage.textContent = "Round over";
    reactionSub.textContent = "Check the results below.";
    nextBtn.classList.toggle("hidden", !currentRoom || currentRoom.host_sid !== mySocketId);
    backBtn.classList.toggle("hidden", !currentRoom || currentRoom.host_sid !== mySocketId);
  }
});
socket.on("game:feedback", result => {
  feedback.textContent = result.type === "early" ? result.message : `Your time: ${result.reaction_ms} ms`;
});
socket.on("game:scores", data => {
  const rows = [];
  data.results.sort((a, b) => a.reaction_ms - b.reaction_ms);
  data.results.forEach((result, index) => rows.push({ name: result.name, text: `${result.reaction_ms} ms`, rank: index + 1 }));
  data.false_starts.forEach(result => rows.push({ name: result.name, text: "False start", rank: 999 }));
  rows.sort((a, b) => a.rank - b.rank);
  scoresList.replaceChildren();
  if (!rows.length) { scoresList.innerHTML = '<p class="muted">No results yet.</p>'; return; }
  rows.forEach((row, index) => {
    const item = document.createElement("div"); item.className = "score-row";
    const name = document.createElement("span"); name.textContent = `${index === 0 && row.rank !== 999 ? "🏆 " : ""}${row.name}`;
    const score = document.createElement("strong"); score.textContent = row.text;
    item.append(name, score); scoresList.append(item);
  });
});
socket.on("knockout:state", state => {
  knockoutState = state;
  drawKnockout(state);
  $("knockoutTimer").textContent = `${state.seconds_left} seconds`;
  if (state.phase === "results") {
    gamePhase = "knockout-results";
    $("knockoutMessage").textContent = state.winner ? `${state.winner} wins.` : "Round over. No one won this round.";
    knockoutAgainBtn.classList.toggle("hidden", !currentRoom || currentRoom.host_sid !== mySocketId);
    knockoutBackBtn.classList.toggle("hidden", !currentRoom || currentRoom.host_sid !== mySocketId);
    resetControls();
  } else {
    gamePhase = "knockout";
    $("knockoutMessage").textContent = "Move around and push the other players out.";
  }
});
socket.on("disconnect", () => { resetControls(); showToast("Connection lost. Refresh if you don't reconnect."); });
