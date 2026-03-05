/**
 * Royal 21 - Frontend JavaScript
 * Handles UI, WebSocket communication, and game logic
 */

// ============================================================================
// GLOBAL STATE
// ============================================================================

const GameState = {
    gameId: null,
    playerSeat: 0,
    ws: null,
    currentState: null,
    legalActions: null,
};

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', function () {
    setupEventListeners();
    renderSeats(7);  // Default 7 seats
    updateUI();
});

function setupEventListeners() {
    document.getElementById('createGameBtn').addEventListener('click', showGameModal);
    document.getElementById('startGameBtn').addEventListener('click', startGame);
}

// ============================================================================
// GAME CREATION & SETUP
// ============================================================================

function showGameModal() {
    document.getElementById('gameModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('gameModal').style.display = 'none';
}

async function createGame() {
    const playerCount = parseInt(document.getElementById('playerCount').value);
    const startingStack = parseInt(document.getElementById('startingStack').value);

    try {
        const response = await fetch('/api/games/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                players: playerCount,
                starting_stack: startingStack
            })
        });

        const data = await response.json();
        GameState.gameId = data.game_id;
        GameState.playerSeat = 0;  // Always be seat 0 for now

        closeModal();
        renderSeats(playerCount);
        connectWebSocket();
        addLog('Game created with ' + playerCount + ' players', 'action');
    } catch (error) {
        console.error('Error creating game:', error);
        addLog('Failed to create game', 'error');
    }
}

function connectWebSocket() {
    if (!GameState.gameId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${GameState.gameId}/${GameState.playerSeat}`;

    GameState.ws = new WebSocket(url);

    GameState.ws.onopen = function () {
        console.log('WebSocket connected');
        getGameState();
    };

    GameState.ws.onmessage = function (event) {
        const message = JSON.parse(event.data);

        if (message.type === 'state_update' || message.type === 'state') {
            GameState.currentState = message.data;
            updateUI();
        } else if (message.type === 'legal_actions') {
            GameState.legalActions = message.data;
            updateActionPanel();
        } else if (message.error) {
            addLog('Error: ' + message.error, 'error');
        }
    };

    GameState.ws.onerror = function (error) {
        console.error('WebSocket error:', error);
        addLog('Connection error', 'error');
    };

    GameState.ws.onclose = function () {
        console.log('WebSocket disconnected');
        addLog('Disconnected from server', 'error');
    };
}

// ============================================================================
// GAME ACTIONS
// ============================================================================

async function startGame() {
    if (!GameState.gameId) {
        alert('Create a game first');
        return;
    }

    try {
        const response = await fetch(`/api/games/${GameState.gameId}/start`, {
            method: 'POST'
        });

        const data = await response.json();
        sendAction('start_hand');
        addLog('Game started!', 'action');
    } catch (error) {
        console.error('Error starting game:', error);
        addLog('Failed to start game', 'error');
    }
}

function getGameState() {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    GameState.ws.send(JSON.stringify({ action: 'get_state' }));
}

function getLegalActions() {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) return;
    GameState.ws.send(JSON.stringify({ action: 'get_legal_actions' }));
}

function sendAction(actionType, data = {}) {
    if (!GameState.ws || GameState.ws.readyState !== WebSocket.OPEN) {
        console.error('WebSocket not connected');
        return;
    }

    const message = { action: actionType, ...data };
    console.log('Sending action:', message);
    GameState.ws.send(JSON.stringify(message));
}

window.sendAction = function(actionType) {
    const data = {};

    if (actionType === 'escrow_add') {
        data.amount = parseInt(document.getElementById('escrowAmount').value) || 0;
        sendAction(actionType, data);
    } else if (actionType === 'bet' || actionType === 'raise') {
        if (actionType === 'bet') {
            data.amount = parseInt(document.getElementById('betAmount').value) || 0;
        } else {
            data.raise_to = parseInt(document.getElementById('betAmount').value) || 0;
        }
        sendAction(actionType, data);
    } else {
        sendAction(actionType, data);
    }
};

// ============================================================================
// UI RENDERING
// ============================================================================

function renderSeats(numSeats) {
    const container = document.getElementById('seatsContainer');
    container.innerHTML = '';

    for (let i = 0; i < numSeats; i++) {
        const seatEl = document.createElement('div');
        seatEl.className = 'seat';
        seatEl.id = `seat-${i}`;
        seatEl.innerHTML = `
            <div class="seat-number">Seat ${i + 1}</div>
            <div class="seat-player" id="player-${i}">
                <div class="player-name">Empty</div>
                <div class="player-stack">Stack: -</div>
                <div class="player-circles">
                    <div class="circle-item normal-circle">
                        <span class="circle-label">Normal</span>
                        <span class="circle-amount">0</span>
                    </div>
                    <div class="circle-item escrow-circle">
                        <span class="circle-label">Escrow</span>
                        <span class="circle-amount">0</span>
                    </div>
                </div>
                <div class="player-card" id="card-${i}" style="display: none;">-</div>
            </div>
        `;
        container.appendChild(seatEl);
    }
}

function updateUI() {
    if (!GameState.currentState) return;

    const state = GameState.currentState;

    // Update pot displays
    document.getElementById('normalPot').textContent = state.normal_pot || 0;
    document.getElementById('escrowPot').textContent = state.escrow_pot || 0;
    document.getElementById('tableTotal').textContent = state.table_total || 0;

    // Update phase
    document.getElementById('phaseDisplay').textContent = capitalizePhase(state.phase);

    // Update player seats
    state.players.forEach(player => {
        const playerEl = document.getElementById(`player-${player.seat}`);
        const cardEl = document.getElementById(`card-${player.seat}`);

        if (playerEl) {
            // Update player info
            playerEl.querySelector('.player-name').textContent = player.username;
            playerEl.querySelector('.player-stack').textContent = `Stack: ${player.stack}`;

            // Update circles
            const normalAmount = playerEl.querySelector('.normal-circle .circle-amount');
            const escrowAmount = playerEl.querySelector('.escrow-circle .circle-amount');
            normalAmount.textContent = player.normal_circle;
            escrowAmount.textContent = player.escrow_circle;

            // Update revealed card
            if (player.revealed_card) {
                cardEl.textContent = player.revealed_card;
                cardEl.style.display = 'block';
            } else {
                cardEl.style.display = 'none';
            }

            // Update seat styling
            playerEl.className = 'seat-player';
            if (!player.in_hand) {
                playerEl.classList.add('player-folded');
            }
            if (player.seat === state.current_action) {
                playerEl.classList.add('current-action');
            }
        }
    });

    // Update action info
    if (state.current_action !== undefined) {
        const actionPlayer = state.players[state.current_action];
        document.getElementById('actionDisplay').textContent = actionPlayer ? actionPlayer.username : '-';
    }

    // Update game info
    document.getElementById('seatDisplay').textContent = `Seat ${GameState.playerSeat + 1}`;

    // Update logs
    if (state.logs && state.logs.length > 0) {
        state.logs.forEach(log => {
            addLog(log, 'action');
        });
    }

    // Get legal actions for current player
    if (state.current_action === GameState.playerSeat && state.phase !== 'hand_over') {
        getLegalActions();
    } else {
        showWaitingMessage();
    }
}

function updateActionPanel() {
    if (!GameState.legalActions) return;

    const actions = GameState.legalActions;
    const bettingActions = document.getElementById('bettingActions');
    const drawActions = document.getElementById('drawActions');
    const waitingMsg = document.getElementById('waitingMessage');

    // Hide all action groups first
    bettingActions.style.display = 'none';
    drawActions.style.display = 'none';
    waitingMsg.style.display = 'none';

    if (actions.error) {
        waitingMsg.style.display = 'block';
        return;
    }

    // Show appropriate action group based on current phase
    if (actions.actions && actions.actions.length > 0) {
        // Betting phase
        bettingActions.style.display = 'block';

        // Update max bet amount
        if (actions.max_raise_to) {
            const betInput = document.getElementById('betAmount');
            betInput.max = actions.max_raise_to;
            betInput.placeholder = `1-${actions.max_raise_to}`;
        }

        // Update escrow options
        const escrowInput = document.getElementById('escrowAmount');
        if (actions.escrow_options && actions.escrow_options.length > 0) {
            escrowInput.max = Math.max(...actions.escrow_options);
            escrowInput.disabled = false;
        } else {
            escrowInput.disabled = true;
        }
    }

    if (actions.hit || actions.stand) {
        // Draw phase
        drawActions.style.display = 'block';

        // Disable buttons based on legal actions
        drawActions.querySelectorAll('button').forEach(btn => {
            const action = btn.textContent.toLowerCase();
            if (action === 'hit' && !actions.hit) btn.disabled = true;
            if (action === 'stand' && !actions.stand) btn.disabled = true;
            if (action === 'double' && !actions.double) btn.disabled = true;
            if (action === 'split' && !actions.split) btn.disabled = true;
        });
    }

    if (bettingActions.style.display === 'none' && drawActions.style.display === 'none') {
        waitingMsg.style.display = 'block';
    }
}

function showWaitingMessage() {
    const bettingActions = document.getElementById('bettingActions');
    const drawActions = document.getElementById('drawActions');
    const waitingMsg = document.getElementById('waitingMessage');

    bettingActions.style.display = 'none';
    drawActions.style.display = 'none';
    waitingMsg.style.display = 'block';
}

// ============================================================================
// UTILITIES
// ============================================================================

function capitalizePhase(phase) {
    return phase.charAt(0).toUpperCase() + phase.slice(1);
}

function addLog(message, type = 'log') {
    const logContent = document.getElementById('logContent');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = message;

    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;

    // Keep only last 50 entries
    while (logContent.children.length > 50) {
        logContent.removeChild(logContent.firstChild);
    }
}
