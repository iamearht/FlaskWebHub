"""
FastAPI backend for Royal 21 - multiplayer poker/blackjack hybrid.
"""
from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Dict, Set, Optional
import json
import logging
from engine import GameEngine
from game_state import ActionType

# ============================================================================
# SETUP
# ============================================================================

app = FastAPI(title="Royal 21")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory games (in production, use database)
games: Dict[str, GameEngine] = {}
player_games: Dict[str, str] = {}  # player_id -> game_id
game_connections: Dict[str, Set[WebSocket]] = {}  # game_id -> set of websockets

# Serve static files
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
except:
    logger.warning("Frontend directory not found")


# ============================================================================
# HTTP ROUTES
# ============================================================================

@app.get("/")
async def root():
    """Serve frontend."""
    return FileResponse("frontend/index.html", media_type="text/html")


@app.post("/api/games/create")
async def create_game(players: int = 2, starting_stack: int = 200):
    """Create a new game."""
    import uuid
    game_id = str(uuid.uuid4())
    seed = hash(game_id) % 100000  # Deterministic seed from game_id

    games[game_id] = GameEngine(game_id, players, starting_stack, seed=seed)
    game_connections[game_id] = set()

    logger.info(f"Created game {game_id} with {players} players")
    return {"game_id": game_id, "status": "created"}


@app.get("/api/games/{game_id}")
async def get_game(game_id: str, player_seat: int = 0):
    """Get current game state."""
    if game_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")

    engine = games[game_id]
    return engine.state_for_player(player_seat)


# ============================================================================
# WEBSOCKET ROUTES
# ============================================================================

@app.websocket("/ws/{game_id}/{player_seat}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_seat: int):
    """WebSocket connection for real-time game updates."""
    if game_id not in games:
        await websocket.close(code=4000, reason="Game not found")
        return

    await websocket.accept()
    logger.info(f"Player {player_seat} connected to game {game_id}")

    game_connections[game_id].add(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            action_type = message.get("action")

            engine = games[game_id]

            # Handle actions
            if action_type == "start_hand":
                engine.start_hand()
                await broadcast_game_state(game_id)

            elif action_type == "escrow_add":
                amount = message.get("amount", 0)
                success, msg = engine.take_action(
                    player_seat,
                    ActionType.ESCROW_ADD,
                    amount=amount
                )
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "fold":
                success, msg = engine.take_action(player_seat, ActionType.FOLD)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "check":
                success, msg = engine.take_action(player_seat, ActionType.CHECK)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "call":
                success, msg = engine.take_action(player_seat, ActionType.CALL)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "bet":
                amount = message.get("amount", 0)
                success, msg = engine.take_action(
                    player_seat,
                    ActionType.BET,
                    amount=amount
                )
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "raise":
                raise_to = message.get("raise_to", 0)
                success, msg = engine.take_action(
                    player_seat,
                    ActionType.RAISE,
                    raise_to=raise_to
                )
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "stand":
                success, msg = engine.take_action(player_seat, ActionType.STAND)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "hit":
                success, msg = engine.take_action(player_seat, ActionType.HIT)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "double":
                success, msg = engine.take_action(player_seat, ActionType.DOUBLE)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "split":
                success, msg = engine.take_action(player_seat, ActionType.SPLIT)
                if success:
                    await broadcast_game_state(game_id)
                else:
                    await websocket.send_json({"error": msg})

            elif action_type == "get_state":
                state = engine.state_for_player(player_seat)
                await websocket.send_json({"type": "state", "data": state})

            elif action_type == "get_legal_actions":
                actions = engine.get_legal_actions(player_seat)
                await websocket.send_json({"type": "legal_actions", "data": actions})

            else:
                await websocket.send_json({"error": f"Unknown action: {action_type}"})

    except WebSocketDisconnect:
        logger.info(f"Player {player_seat} disconnected from game {game_id}")
        game_connections[game_id].discard(websocket)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def broadcast_game_state(game_id: str):
    """Broadcast updated game state to all connected clients."""
    if game_id not in games or game_id not in game_connections:
        return

    engine = games[game_id]
    # Send state to each player (seat-specific)
    for websocket in game_connections[game_id].copy():
        try:
            # In full impl, would track which player is on which websocket
            state = engine.state_for_player(0)  # Simplified
            await websocket.send_json({"type": "state_update", "data": state})
        except Exception as e:
            logger.error(f"Error broadcasting to {game_id}: {e}")
            game_connections[game_id].discard(websocket)


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info("Royal 21 server starting...")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Royal 21 server shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
