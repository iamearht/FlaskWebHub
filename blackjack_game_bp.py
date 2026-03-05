"""
Flask blueprint for Two-Circle Royal 21 free-play game mode.

Provides routes for:
- Joining tables
- Viewing table state
- Taking player actions
- Game updates
"""

from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required, current_user
from extensions import db
from models import User
from blackjack_game_engine import (
    BlackjackGameEngine,
    GamePhase,
    ActionType,
)

# Simple in-memory table store (for demo; in production use DB)
TABLES = {}  # table_id -> BlackjackGameEngine instance
TABLE_COUNTER = 0

blackjack_bp = Blueprint("blackjack", __name__, url_prefix="/blackjack")


# ============================================================================
# TABLE MANAGEMENT
# ============================================================================

@blackjack_bp.route("/lobby", methods=["GET"])
@login_required
def blackjack_lobby():
    """Display free blackjack lobby"""
    available_tables = [
        {
            "table_id": table_id,
            "seats": len(engine.game_state.players) if engine.game_state else 0,
            "status": "waiting" if engine and engine.game_state and engine.game_state.phase == GamePhase.SETUP else "active",
        }
        for table_id, engine in TABLES.items()
    ]

    return render_template(
        "blackjack_lobby.html",
        user=current_user,
        available_tables=available_tables,
    )


@blackjack_bp.route("/create_table", methods=["POST"])
@login_required
def create_table():
    """Create a new table with specified players"""
    global TABLE_COUNTER

    data = request.get_json() or {}
    num_seats = int(data.get("num_seats", 7))

    if num_seats < 2 or num_seats > 7:
        return jsonify({"error": "Table must have 2-7 seats"}), 400

    TABLE_COUNTER += 1
    table_id = TABLE_COUNTER

    # Initialize with current user + AI/empty seats
    players = [(current_user.id, current_user.username)]
    # Add empty seats
    for i in range(1, num_seats):
        players.append((0, f"Empty Seat {i}"))

    engine = BlackjackGameEngine(seed=table_id)  # Deterministic seed
    engine.create_table(players, initial_stack=1000)

    TABLES[table_id] = engine

    return jsonify({
        "table_id": table_id,
        "message": "Table created",
    })


@blackjack_bp.route("/table/<int:table_id>", methods=["GET"])
@login_required
def view_table(table_id):
    """View a specific table"""
    if table_id not in TABLES:
        abort(404, "Table not found")

    engine = TABLES[table_id]

    return render_template(
        "blackjack_table.html",
        table_id=table_id,
        user=current_user,
    )


@blackjack_bp.route("/api/table/<int:table_id>/state", methods=["GET"])
@login_required
def get_table_state(table_id):
    """Get current table state"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    engine = TABLES[table_id]
    return jsonify(engine.get_state())


@blackjack_bp.route("/api/table/<int:table_id>/start_hand", methods=["POST"])
@login_required
def start_hand(table_id):
    """Start a new hand at the table"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    engine = TABLES[table_id]

    try:
        engine.start_hand()
        return jsonify({"message": "Hand started", "state": engine.get_state()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@blackjack_bp.route("/api/table/<int:table_id>/action", methods=["POST"])
@login_required
def take_action(table_id):
    """Take a player action"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    engine = TABLES[table_id]
    data = request.get_json() or {}

    seat = int(data.get("seat"))
    action_name = data.get("action")
    amount = int(data.get("amount", 0))

    # Get current player
    player = next((p for p in engine.game_state.players if p.seat == seat), None)
    if not player or player.user_id != current_user.id:
        return jsonify({"error": "Not your seat"}), 403

    try:
        action = ActionType[action_name.upper()]
        engine.player_action(seat, action, amount)
        return jsonify({"state": engine.get_state()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": f"Unknown action: {action_name}"}), 400


@blackjack_bp.route("/api/table/<int:table_id>/advance_phase", methods=["POST"])
@login_required
def advance_phase(table_id):
    """Advance to next phase"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    engine = TABLES[table_id]

    try:
        engine.phase_complete_check()
        return jsonify({"state": engine.get_state()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
