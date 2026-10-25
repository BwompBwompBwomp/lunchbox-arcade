const socket = io();

const $ = id => document.getElementById(id);
const setup = $("setup");
const roomPanel = $("roomPanel");
const gamePanel = $("gamePanel");
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

let currentRoom = null;
let mySocketId = null;
let gamePhase = "lobby";
let toastTimeout;

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.add("hidden"), 2800);
}
function nameValue() {
  const value = playerName.value.trim().slice(0, 16);
  if (!value) { playerName.focus(); showToast("Choose a display name first."); return null; }
  return value;
}
function showRoom(room) {
  currentRoom = room;
  setup.classList.add("hidden");
  roomPanel.classList.remove("hidden");
  $("roomCodeDisplay").textContent = room.code;
  $("roomStatus").textContent = room.status === "playing" ? "Game in progress" : `${room.players.length}/8 players in the room`;
  $("playersList").replaceChildren();
  room.players.forEach(player => {
    const card = document.createElement("div");
    card.className = "player";
    const name = document.createElement("div");
    name.className = "player-name";
    name.textContent = player.name;
    const role = document.createElement("div");
    role.className = "player-role";
    role.textContent = player.is_host ? "★ HOST" : "PLAYER";
    card.append(name, role);
    $("playersList").append(card);
  });
  const isHost = room.host_sid === mySocketId;
  startBtn.disabled = !isHost || room.players.length < 2 || room.status === "playing";
  startBtn.textContent = room.status === "playing" ? "Game in progress" : (isHost ? "Start Reaction Race" : "Waiting for host…");
  startBtn.classList.toggle("hidden", room.status === "playing");
  if (room.status === "playing") gamePanel.classList.remove("hidden");
  else if (gamePhase === "lobby") gamePanel.classList.add("hidden");
}
function resetGameView() {
  gamePhase = "lobby";
  gamePanel.classList.add("hidden");
  nextBtn.classList.add("hidden");
  backBtn.classList.add("hidden");
  feedback.textContent = "";
  scoresList.innerHTML = '<p class="muted">Your results will appear here.</p>';
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
roomCodeInput.addEventListener("input", () => {
  roomCodeInput.value = roomCodeInput.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 5);
});
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
  try { await navigator.clipboard.writeText(currentRoom.code); showToast("Room code copied!"); }
  catch { showToast(`Your room code is ${currentRoom.code}`); }
});
reactionPad.addEventListener("click", () => {
  if (gamePhase === "waiting" || gamePhase === "go") socket.emit("game:react");
});
nextBtn.addEventListener("click", () => socket.emit("game:next"));
backBtn.addEventListener("click", () => {
  socket.emit("game:back-to-lobby");
  resetGameView();
});

socket.on("connect", () => { mySocketId = socket.id; });
socket.on("room:joined", room => { showRoom(room); showToast(`Joined room ${room.code}`); });
socket.on("room:update", room => {
  showRoom(room);
  if (room.status === "lobby" && gamePhase !== "lobby") resetGameView();
});
socket.on("app:error", message => showToast(message));
socket.on("game:state", state => {
  gamePhase = state.phase;
  gamePanel.classList.remove("hidden");
  $("roundLabel").textContent = state.round_number ? `Round ${state.round_number}` : "Lobby";
  reactionPad.className = "reaction-pad";
  feedback.textContent = "";
  if (state.phase === "waiting") {
    reactionPad.classList.add("waiting");
    reactionEmoji.textContent = "⏱️";
    reactionMessage.textContent = "Get ready…";
    reactionSub.textContent = "Wait for green. Clicking early counts against you.";
    nextBtn.classList.add("hidden"); backBtn.classList.add("hidden");
    scoresList.innerHTML = '<p class="muted">Waiting for the round to finish…</p>';
  } else if (state.phase === "go") {
    reactionPad.classList.add("go");
    reactionEmoji.textContent = "⚡";
    reactionMessage.textContent = "CLICK NOW!";
    reactionSub.textContent = "Click this panel as quickly as you can.";
  } else if (state.phase === "results") {
    reactionPad.classList.add("results");
    reactionEmoji.textContent = "🏁";
    reactionMessage.textContent = "Round over!";
    reactionSub.textContent = "Check the results below.";
    nextBtn.classList.toggle("hidden", !currentRoom || currentRoom.host_sid !== mySocketId);
    backBtn.classList.toggle("hidden", !currentRoom || currentRoom.host_sid !== mySocketId);
  } else if (state.phase === "lobby") resetGameView();
});
socket.on("game:feedback", result => {
  feedback.textContent = result.type === "early" ? result.message : `Your reaction time: ${result.reaction_ms} ms`;
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
socket.on("disconnect", () => showToast("Connection lost. Refresh if you don't reconnect."));
