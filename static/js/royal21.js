"use strict";

// CURRENT_USER = {id: "...", name: "..."}
// TABLE_CONFIG  = {id: N, ante: N, min_buyin: N, max_buyin: N, name: "..."}
// HAS_SEAT      = true | false

const S = {
  socket: null,
  tableId: TABLE_CONFIG.id,
  mySeat: null,
  privateState: null,
  publicState: null,
  pendingRaiseAction: null,
  lastActionStateId: null,
};

// ─── Screen management ──────────────────────────────────────────
const SCREENS = ["seat", "ready", "game"];

function showScreen(name) {
  SCREENS.forEach(s => {
    const el = document.getElementById(`screen-${s}`);
    if (el) el.classList.add("r21-hidden");
  });
  const target = document.getElementById(`screen-${name}`);
  if (target) target.classList.remove("r21-hidden");
}

// ─── Status bar ─────────────────────────────────────────────────
function setStatus(text, state) {
  const textEl = document.getElementById("r21-status-text");
  if (textEl) textEl.textContent = text;
  const dot = document.getElementById("r21-status-dot");
  if (!dot) return;
  dot.className = "";
  if (state === "connected") dot.classList.add("connected");
  if (state === "error")     dot.classList.add("error");
}

// ─── Error flash ─────────────────────────────────────────────────
function flashError(msg) {
  const el = document.getElementById("r21-error-flash");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("r21-hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("r21-hidden"), 4000);
}

// ─── Log ─────────────────────────────────────────────────────────
function addLog(msg) {
  const body = document.getElementById("r21-log-body");
  if (!body) return;
  const entry = document.createElement("div");
  entry.className = "r21-log-entry";
  const ts = new Date().toLocaleTimeString("en-US", {hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit"});
  entry.textContent = `[${ts}] ${msg}`;
  body.prepend(entry);
  while (body.children.length > 100) body.removeChild(body.lastChild);
}

// ─── Socket setup ────────────────────────────────────────────────
function initSocket() {
  S.socket = io();

  S.socket.on("connect", () => {
    setStatus("Connected", "connected");
    addLog("Connected to server.");
    // Request current state (handles reconnect or fresh load)
    S.socket.emit("royal21_get_state", {table_id: S.tableId});
  });

  S.socket.on("disconnect", () => {
    setStatus("Disconnected", "error");
    flashError("Connection lost. Please refresh the page.");
  });

  S.socket.on("royal21_no_seat", () => {
    // Not seated at this table — show seat selection
    showScreen("seat");
    // Render with empty state
    renderSeatScreen({players: [], available_seats: [0,1,2,3,4,5,6]});
  });

  S.socket.on("royal21_state", (payload) => {
    S.publicState = payload;
    // Use private state if we have it (it has our cards), else public
    const stateToRender = S.privateState || payload;
    handleState(stateToRender);
  });

  S.socket.on("royal21_private", (payload) => {
    S.privateState = payload;
    handleState(payload);
  });

  S.socket.on("royal21_error", (payload) => {
    flashError(payload.message || "Error");
    addLog("Error: " + (payload.message || "Unknown error"));
  });
}

// ─── State handler ───────────────────────────────────────────────
function handleState(state) {
  const phase = state.phase || "WAITING";
  const myPlayer = getMyPlayer(state);

  if (myPlayer) S.mySeat = myPlayer.seat;

  if (phase === "WAITING" || phase === "HAND_END") {
    if (!myPlayer) {
      showScreen("seat");
      renderSeatScreen(state);
    } else {
      showScreen("ready");
      renderReadyScreen(state);
    }
  } else {
    showScreen("game");
    renderGame(state);
  }
}

function getMyPlayer(state) {
  const players = state.players || [];
  return players.find(p => String(p.player_id) === String(CURRENT_USER.id)) || null;
}

// ─── Seat Screen ─────────────────────────────────────────────────
function renderSeatScreen(state) {
  const players = state.players || [];
  const occupiedSeats = {};
  players.forEach(p => { occupiedSeats[p.seat] = p; });
  const available = state.available_seats || [];

  const grid = document.getElementById("seat-grid");
  if (!grid) return;
  grid.innerHTML = "";

  for (let i = 0; i < 7; i++) {
    const btn = document.createElement("div");
    btn.className = "r21-seat-btn";
    const isAvailable = available.includes(i);
    const occupant = occupiedSeats[i];

    if (isAvailable) {
      btn.classList.add("empty");
      btn.innerHTML = `<div class="seat-num">${i}</div><div class="seat-name">Empty</div>`;
      btn.addEventListener("click", () => joinWithSeat(i));
    } else if (occupant) {
      btn.classList.add("taken");
      btn.innerHTML = `<div class="seat-num">${i}</div><div class="seat-name">${esc(occupant.name)}</div><div class="seat-name">${occupant.stack} coins</div>`;
    } else {
      btn.classList.add("unavailable");
      btn.innerHTML = `<div class="seat-num">${i}</div><div class="seat-name">N/A</div>`;
    }
    grid.appendChild(btn);
  }
}

function joinWithSeat(seatNum) {
  const buyinInput = document.getElementById("inp-buyin");
  if (!buyinInput) return;
  const buyin = parseInt(buyinInput.value);
  if (!buyin || buyin < TABLE_CONFIG.min_buyin || buyin > TABLE_CONFIG.max_buyin) {
    flashError(`Buy-in must be between ${TABLE_CONFIG.min_buyin} and ${TABLE_CONFIG.max_buyin} coins`);
    return;
  }
  S.mySeat = seatNum;
  S.socket.emit("royal21_join", {
    table_id: S.tableId,
    buyin: buyin,
    seat: seatNum,
  });
  addLog(`Joining seat ${seatNum} with ${buyin} coins...`);
}

// ─── Ready Screen ────────────────────────────────────────────────
function renderReadyScreen(state) {
  const players = state.players || [];
  const readySeats = state.ready_seats || [];
  const myPlayer = getMyPlayer(state);
  if (myPlayer) S.mySeat = myPlayer.seat;

  const list = document.getElementById("r21-seated-list");
  if (list) {
    list.innerHTML = "";
    players.forEach(p => {
      const row = document.createElement("div");
      row.className = "r21-seated-row";
      const readyText = readySeats.includes(p.seat) ? "✓ Ready" : "Waiting...";
      row.innerHTML = `<span>Seat ${p.seat}: ${esc(p.name)}</span><span>${readyText}</span>`;
      list.appendChild(row);
    });
  }

  const readyBtn = document.getElementById("btn-ready");
  if (readyBtn) {
    if (myPlayer && readySeats.includes(myPlayer.seat)) {
      readyBtn.disabled = true;
      readyBtn.textContent = "Waiting for others...";
    } else {
      readyBtn.disabled = false;
      readyBtn.textContent = "I'm Ready";
    }
  }
}

// ─── Ready button ────────────────────────────────────────────────
(function() {
  const btn = document.getElementById("btn-ready");
  if (btn) {
    btn.addEventListener("click", () => {
      S.socket.emit("royal21_ready", {table_id: S.tableId});
      btn.disabled = true;
      btn.textContent = "Waiting for others...";
      addLog("Sent: I'm ready.");
    });
  }
})();

// ─── Game Screen ─────────────────────────────────────────────────
function renderGame(state) {
  const phase          = state.phase || "—";
  const handNum        = state.hand_number || 0;
  const buttonSeat     = state.button_seat;
  const pot            = state.pot || 0;
  const highBet        = state.current_high_bet || 0;
  const currentActor   = state.current_actor;
  const players        = state.players || [];
  const legalActions   = state.legal_actions || [];

  // Header
  const gPhase = document.getElementById("g-phase");
  const gHand  = document.getElementById("g-hand");
  const gBtn   = document.getElementById("g-button");
  const gPot   = document.getElementById("g-pot");
  const gHigh  = document.getElementById("g-highbet");
  const gPend  = document.getElementById("g-pending");

  if (gPhase) gPhase.textContent = phase;
  if (gHand)  gHand.textContent  = `#${handNum}`;
  if (gBtn)   gBtn.textContent   = (buttonSeat !== null && buttonSeat !== undefined) ? buttonSeat : "—";
  if (gPot)   gPot.textContent   = pot;
  if (gHigh)  gHigh.textContent  = highBet;

  let pendingTotal = 0;
  players.forEach(p => { pendingTotal += (p.current_bet || 0); });
  if (gPend) gPend.textContent = pendingTotal;

  renderPlayersTable(players, buttonSeat, currentActor, phase);
  renderYourHand(players, phase);

  if (phase === "SHOWDOWN" && state.showdown_result) {
    renderShowdown(state);
  } else {
    const sp = document.getElementById("showdown-panel");
    if (sp) sp.classList.add("r21-hidden");
  }

  // Action panel
  const myPlayer = getMyPlayer(state);
  const isMyTurn = myPlayer && String(myPlayer.seat) === String(currentActor) && legalActions.length > 0;
  const actionStateId = `${phase}|${currentActor}|${legalActions.length}`;

  if (isMyTurn && actionStateId !== S.lastActionStateId) {
    S.lastActionStateId = actionStateId;
    renderActionButtons(legalActions, players, currentActor, phase);
  } else if (!isMyTurn) {
    S.pendingRaiseAction = null;
    const raisePanel    = document.getElementById("raise-panel");
    const actionButtons = document.getElementById("action-buttons");
    const actionWaiting = document.getElementById("action-waiting");
    if (raisePanel)    raisePanel.classList.add("r21-hidden");
    if (actionButtons) actionButtons.classList.add("r21-hidden");
    if (actionWaiting) {
      actionWaiting.classList.remove("r21-hidden");
      if (phase === "SHOWDOWN") {
        actionWaiting.textContent = "Showdown";
      } else if (phase === "HAND_END") {
        actionWaiting.textContent = "Hand ended — next hand starting soon...";
      } else if (currentActor !== null && currentActor !== undefined) {
        const actingPlayer = players.find(p => p.seat === currentActor);
        actionWaiting.textContent = actingPlayer
          ? `Waiting for ${actingPlayer.name} (Seat ${currentActor})...`
          : `Waiting for Seat ${currentActor}...`;
      } else {
        actionWaiting.textContent = "Waiting...";
      }
    }
  }

  addLog(`[${phase}] Hand #${handNum} · Pot: ${pot} · Actor: ${currentActor !== null && currentActor !== undefined ? `Seat ${currentActor}` : "none"}`);
}

function renderPlayersTable(players, buttonSeat, currentActor, phase) {
  const tbody = document.getElementById("players-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const sorted = [...players].sort((a, b) => a.seat - b.seat);
  sorted.forEach(p => {
    const seat     = p.seat;
    const isMe     = String(p.player_id) === String(CURRENT_USER.id);
    const isActing = seat === currentActor;
    const isButton = seat === buttonSeat;

    const tr = document.createElement("tr");
    if (isMe)       tr.classList.add("is-me");
    if (isActing)   tr.classList.add("is-acting");
    if (p.is_folded) tr.classList.add("is-folded");

    let nameBadges = "";
    if (isButton)   nameBadges += `<span class="r21-badge r21-badge-btn">BTN</span>`;
    if (isMe)       nameBadges += `<span class="r21-badge r21-badge-you">YOU</span>`;
    if (p.is_folded) nameBadges += `<span class="r21-badge r21-badge-fold">FOLD</span>`;
    if (p.is_all_in) nameBadges += `<span class="r21-badge r21-badge-allin">ALL-IN</span>`;
    if (p.is_bust)   nameBadges += `<span class="r21-badge r21-badge-fold">BUST</span>`;

    let cardsHtml = "";
    const holeCards = p.hole_cards || [];
    holeCards.forEach(c => {
      cardsHtml += (c.display === "??")
        ? `<span class="r21-card-chip">??</span>`
        : `<span class="r21-card-chip">${esc(c.display)}</span>`;
    });

    tr.innerHTML = `
      <td>${seat}${isActing ? ' <span style="color:#f39c12;font-weight:700">→</span>' : ''}</td>
      <td>${esc(p.name || `Seat ${seat}`)}${nameBadges}</td>
      <td style="font-family:monospace;font-weight:600">${p.stack !== undefined ? p.stack : '—'}</td>
      <td style="font-family:monospace">${p.current_bet || 0}</td>
      <td>${cardsHtml}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderYourHand(players, phase) {
  const container = document.getElementById("hand-cards");
  if (!container) return;
  if (S.mySeat === null) {
    container.innerHTML = '<span style="color:#aaa">Not seated</span>';
    return;
  }

  const me = players.find(p => p.seat === S.mySeat);
  if (!me) {
    container.innerHTML = '<span style="color:#aaa">—</span>';
    return;
  }

  const holeCards = me.hole_cards || [];
  if (!holeCards.length) {
    container.innerHTML = '<span style="color:#aaa;font-size:0.9rem">No cards yet</span>';
    return;
  }

  container.innerHTML = "";
  holeCards.forEach(card => {
    if (card.display === "??") {
      const el = document.createElement("div");
      el.className = "r21-hand-card";
      el.innerHTML = `<span class="card-rank">?</span><span class="card-suit">?</span>`;
      container.appendChild(el);
    } else {
      container.appendChild(makeCardEl(card.display));
    }
  });

  // Hand total value
  if (me.hand_value !== undefined && me.hand_value !== null) {
    const valEl = document.createElement("div");
    valEl.style.cssText = "display:flex;flex-direction:column;align-items:center";
    const isBust = me.is_bust;
    valEl.innerHTML = `
      <div class="r21-hand-value${isBust ? " bust" : ""}">${isBust ? "BUST" : me.hand_value}</div>
      <div class="r21-hand-label">${isBust ? "Bust" : "Total"}</div>
    `;
    container.appendChild(valEl);
  }
}

function makeCardEl(cardStr, clickable, onClickFn) {
  const el = document.createElement("div");
  el.className = "r21-hand-card";
  if (clickable) el.classList.add("clickable");

  const suitChar  = cardStr.slice(-1);
  const rankStr   = cardStr.slice(0, -1);
  const suitClass = suitToClass(suitChar);
  if (suitClass) el.classList.add(suitClass);

  el.innerHTML = `<span class="card-rank">${esc(rankStr)}</span><span class="card-suit">${esc(suitChar)}</span>`;
  if (clickable && onClickFn) el.addEventListener("click", onClickFn);
  return el;
}

function suitToClass(suit) {
  if (suit === "♠" || suit === "S") return "spades";
  if (suit === "♣" || suit === "C") return "clubs";
  if (suit === "♥" || suit === "H") return "hearts";
  if (suit === "♦" || suit === "D") return "diamonds";
  return "";
}

function renderShowdown(state) {
  const panel    = document.getElementById("showdown-panel");
  const tbody    = document.getElementById("showdown-tbody");
  const title    = document.getElementById("showdown-title");
  const stacksEl = document.getElementById("showdown-stacks");
  if (!panel) return;

  panel.classList.remove("r21-hidden");
  const result    = state.showdown_result || {};
  const winners   = result.winners || [];
  const dist      = result.distribution || {};
  const handDisps = result.hand_displays || {};
  const players   = state.players || [];

  if (title) title.textContent = "Showdown";
  if (tbody) {
    tbody.innerHTML = "";
    [...players].sort((a,b) => a.seat - b.seat).forEach(p => {
      const seatStr  = String(p.seat);
      const isWinner = winners.includes(p.seat) || winners.includes(seatStr);
      const tr = document.createElement("tr");
      if (isWinner) tr.classList.add("winner");
      const cards = (p.hole_cards || []).map(c => c.display).join(" ");
      const won   = dist[p.seat] || dist[seatStr] || 0;
      const hDisp = handDisps[seatStr] || "—";
      tr.innerHTML = `
        <td>${p.seat}</td>
        <td>${esc(p.name)}</td>
        <td style="font-family:monospace">${esc(cards)}</td>
        <td>${esc(hDisp)}</td>
        <td class="won-chips">${won > 0 ? "+" + won : "—"}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  if (stacksEl && players.length) {
    const parts = players.map(p => `${esc(p.name)}: ${p.stack}`);
    stacksEl.innerHTML = "Updated stacks: " + parts.join("  ·  ");
  }
}

// ─── Action buttons ───────────────────────────────────────────────
function renderActionButtons(legalActions, players, currentActor, phase) {
  const waitingEl  = document.getElementById("action-waiting");
  const buttonsEl  = document.getElementById("action-buttons");
  const raisePanel = document.getElementById("raise-panel");

  if (waitingEl)  waitingEl.classList.add("r21-hidden");
  if (raisePanel) raisePanel.classList.add("r21-hidden");
  S.pendingRaiseAction = null;

  if (!buttonsEl) return;
  buttonsEl.classList.remove("r21-hidden");
  buttonsEl.innerHTML = "";

  if (!legalActions.length) {
    if (waitingEl) { waitingEl.textContent = "No actions available."; waitingEl.classList.remove("r21-hidden"); }
    buttonsEl.classList.add("r21-hidden");
    return;
  }

  legalActions.forEach(action => {
    const aType = action.action;
    let btn;

    if (aType === "fold") {
      btn = makeBtn("Fold", "r21-btn-fold", () => doAction("fold"));
    } else if (aType === "check") {
      btn = makeBtn("Check", "r21-btn-check", () => doAction("check"));
    } else if (aType === "call") {
      const label = action.is_all_in ? `Call ${action.amount} (All-in)` : `Call ${action.amount}`;
      btn = makeBtn(label, "r21-btn-call", () => doAction("call", action.amount));
    } else if (aType === "raise") {
      btn = makeBtn("Raise ▼", "r21-btn-raise", () => showRaisePanel(action));
    } else if (aType === "hit") {
      btn = makeBtn("Hit", "r21-btn-hit", () => doAction("hit"));
    } else if (aType === "stand") {
      btn = makeBtn("Stand", "r21-btn-stand", () => doAction("stand"));
    } else {
      btn = makeBtn(aType, "r21-btn-secondary", () => doAction(aType));
    }

    if (btn) buttonsEl.appendChild(btn);
  });
}

function makeBtn(text, className, onClick) {
  const btn = document.createElement("button");
  btn.className = `r21-btn ${className}`;
  btn.textContent = text;
  btn.addEventListener("click", onClick);
  return btn;
}

function doAction(actionType, amount, cardIndex) {
  if (amount === undefined) amount = null;
  if (cardIndex === undefined) cardIndex = null;

  const payload = {table_id: S.tableId, action_type: actionType, amount: amount};
  if (cardIndex !== null) payload.card_index = cardIndex;
  S.socket.emit("royal21_action", payload);
  addLog(`Action sent: ${actionType}${amount !== null ? " " + amount : ""}`);

  // Disable buttons to prevent double-send
  const buttonsEl = document.getElementById("action-buttons");
  if (buttonsEl) buttonsEl.querySelectorAll("button").forEach(b => b.disabled = true);
  const raisePanel = document.getElementById("raise-panel");
  if (raisePanel) raisePanel.classList.add("r21-hidden");
  const waitingEl = document.getElementById("action-waiting");
  if (waitingEl) { waitingEl.textContent = "Action sent, waiting..."; waitingEl.classList.remove("r21-hidden"); }
}

// ─── Raise panel ─────────────────────────────────────────────────
function showRaisePanel(action) {
  S.pendingRaiseAction = action;
  const minVal = action.min;
  const maxVal = action.max;
  const panel  = document.getElementById("raise-panel");
  const slider = document.getElementById("raise-slider");
  const input  = document.getElementById("raise-input");
  if (!panel || !slider || !input) return;

  const lbl = document.getElementById("raise-label");
  if (lbl) lbl.textContent = `Raise amount (${minVal} – ${maxVal})`;
  const minLbl = document.getElementById("raise-min-label");
  const maxLbl = document.getElementById("raise-max-label");
  if (minLbl) minLbl.textContent = minVal;
  if (maxLbl) maxLbl.textContent = maxVal;
  slider.min = minVal;  slider.max = maxVal;  slider.value = minVal;
  input.min  = minVal;  input.max  = maxVal;  input.value  = minVal;

  panel.classList.remove("r21-hidden");
  slider.oninput = () => { input.value = slider.value; };
  input.oninput  = () => {
    let v = parseInt(input.value);
    if (isNaN(v)) return;
    if (v < minVal) v = minVal;
    if (v > maxVal) v = maxVal;
    slider.value = v;
  };
}

(function() {
  const confirmBtn = document.getElementById("btn-raise-confirm");
  if (confirmBtn) {
    confirmBtn.addEventListener("click", () => {
      if (!S.pendingRaiseAction) return;
      const v      = parseInt(document.getElementById("raise-input").value);
      const minVal = S.pendingRaiseAction.min;
      const maxVal = S.pendingRaiseAction.max;
      if (isNaN(v) || v < minVal || v > maxVal) {
        flashError(`Amount must be between ${minVal} and ${maxVal}`);
        return;
      }
      doAction("raise", v);
    });
  }

  const cancelBtn = document.getElementById("btn-raise-cancel");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      const rp = document.getElementById("raise-panel");
      if (rp) rp.classList.add("r21-hidden");
      S.pendingRaiseAction = null;
    });
  }

  document.querySelectorAll(".r21-leave-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (confirm("Are you sure you want to leave? Your remaining chips will be returned to your account.")) {
        S.socket.emit("royal21_leave", {table_id: S.tableId});
        setTimeout(() => { window.location.href = "/game/lobby"; }, 500);
      }
    });
  });
})();

// ─── Card Reveal ─────────────────────────────────────────────────
function handleRevealPrompt(payload) {
  const playerSeat = payload.player_seat;
  const cards      = payload.cards || [];

  if (String(playerSeat) !== String(S.mySeat)) {
    addLog(`Seat ${playerSeat} is choosing a card to reveal...`);
    return;
  }

  const container = document.getElementById("r21-reveal-cards");
  if (!container) return;
  container.innerHTML = "";

  cards.forEach((card, idx) => {
    const cardStr = (card.display || ((card.rank || "") + (card.suit || "")));
    const el = makeCardEl(cardStr, true, () => {
      doAction("reveal", null, idx);
      const overlay = document.getElementById("r21-reveal-overlay");
      if (overlay) overlay.classList.add("r21-hidden");
    });
    container.appendChild(el);
  });

  const overlay = document.getElementById("r21-reveal-overlay");
  if (overlay) overlay.classList.remove("r21-hidden");
}

// ─── Utility ─────────────────────────────────────────────────────
function esc(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ─── Init ─────────────────────────────────────────────────────────
initSocket();
