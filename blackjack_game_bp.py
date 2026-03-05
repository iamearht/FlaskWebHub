"""
Flask blueprint for Two-Circle Royal 21 free-play game mode.

Provides routes for:
- Joining tables
- Viewing table state
- Taking player actions
- Game updates
"""

from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, abort, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User, BlackjackTable, BlackjackTableSeat
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

    # Load table info from database
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        abort(404, "Table not found in database")

    engine = TABLES[table_id]

    # Get seated players from database
    seated_players = BlackjackTableSeat.query.filter_by(table_id=table_id).all()

    return render_template(
        "blackjack_table.html",
        table_id=table_id,
        table=table,
        seated_players=seated_players,
        user=current_user,
    )


@blackjack_bp.route("/api/table/<int:table_id>/state", methods=["GET"])
@login_required
def get_table_state(table_id):
    """Get current table state with seated players from database"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    # Load seated players from database
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found in database"}), 404

    seated_seats = BlackjackTableSeat.query.filter_by(table_id=table_id).all()
    seated_players = [
        {
            "seat": seat.seat_number,
            "username": seat.user.username if seat.user else None,
            "user_id": seat.user_id,
            "joined_at": seat.joined_at.isoformat() if seat.joined_at else None,
        }
        for seat in seated_seats
        if seat.user_id is not None
    ]

    engine = TABLES[table_id]
    game_state = engine.get_state()

    # Merge database seating with game engine state
    return jsonify({
        "phase": game_state.get("phase", "setup"),
        "current_player_seat": game_state.get("current_player_seat"),
        "button_seat": game_state.get("button_seat"),
        "seated_players": seated_players,
        "game_state": game_state,
        "normal_pot": game_state.get("normal_pot", 0),
        "escrow_pot": game_state.get("escrow_pot", 0),
    })


@blackjack_bp.route("/api/join_seat/<int:table_id>/<int:seat_number>", methods=["POST"])
@login_required
def join_seat(table_id, seat_number):
    """Join a specific seat at a table"""
    # Find the table in database
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found"}), 404

    # Check if seat number is valid
    if seat_number < 0 or seat_number >= table.max_seats:
        return jsonify({"error": "Invalid seat number"}), 400

    # Find the seat
    seat = BlackjackTableSeat.query.filter_by(
        table_id=table_id,
        seat_number=seat_number
    ).first()

    if not seat:
        return jsonify({"error": "Seat not found"}), 404

    # Check if seat is already occupied
    if seat.user_id is not None:
        return jsonify({"error": "Seat already occupied"}), 409

    # Check if user is already seated at this table
    existing_seat = BlackjackTableSeat.query.filter_by(
        table_id=table_id,
        user_id=current_user.id
    ).first()

    if existing_seat:
        return jsonify({"error": "You are already seated at this table"}), 409

    # Seat the player
    seat.user_id = current_user.id
    seat.joined_at = datetime.utcnow()
    db.session.commit()

    # Auto-start hand if 2+ players are now seated
    seated_count = BlackjackTableSeat.query.filter_by(table_id=table_id).filter(
        BlackjackTableSeat.user_id.isnot(None)
    ).count()

    auto_started = False
    if seated_count >= 2 and table_id in TABLES:
        engine = TABLES[table_id]
        if engine.game_state is None or engine.game_state.phase == GamePhase.SETUP:
            try:
                engine.start_hand()
                auto_started = True
            except Exception as e:
                current_app.logger.warning(f"Failed to auto-start hand: {e}")

    # Return seat info
    return jsonify({
        "status": "seated",
        "table_id": table_id,
        "seat_number": seat_number,
        "user_id": current_user.id,
        "username": current_user.username,
        "seat_count": table.seat_count,
        "auto_started": auto_started
    })


@blackjack_bp.route("/api/leave_seat/<int:table_id>", methods=["POST"])
@login_required
def leave_seat(table_id):
    """Leave a table"""
    # Find the table
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found"}), 404

    # Find user's seat at this table
    seat = BlackjackTableSeat.query.filter_by(
        table_id=table_id,
        user_id=current_user.id
    ).first()

    if not seat:
        return jsonify({"error": "You are not seated at this table"}), 404

    # Remove player from seat
    seat.user_id = None
    seat.joined_at = None
    db.session.commit()

    return jsonify({"status": "left", "table_id": table_id})


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
