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
from blackjack_game_engine import GameEngine, GamePhase, ActionType

# Simple in-memory table store (for demo; in production use DB)
TABLES = {}             # table_id -> GameEngine instance
TABLE_COUNTER = 0
PLAYER_READY_STATUS = {}  # table_id -> {user_id: bool}

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
            "status": (
                "waiting"
                if engine
                and engine.game_state
                and engine.game_state.phase == GamePhase.SETUP
                else "active"
            ),
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
    num_seats = int(data.get("num_seats", 5))

    if num_seats < 2 or num_seats > 5:
        return jsonify({"error": "Table must have 2-5 seats"}), 400

    TABLE_COUNTER += 1
    table_id = TABLE_COUNTER

    # Initialize with current user + empty seats
    players = [(0, current_user.id, current_user.username)]
    for i in range(1, num_seats):
        players.append((i, 0, f"Empty Seat {i}"))

    engine = GameEngine(seed=table_id)  # Deterministic seed
    engine.create_table(players, initial_stack=1000)

    TABLES[table_id] = engine

    return jsonify({"table_id": table_id, "message": "Table created"})


@blackjack_bp.route("/table/<int:table_id>", methods=["GET"])
@login_required
def view_table(table_id):
    """View a specific table (with lazy initialization)"""
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        abort(404, "Table not found")

    if table_id not in TABLES:
        try:
            engine = GameEngine(seed=table_id)
            TABLES[table_id] = engine
            current_app.logger.info(f"Game engine initialized for table {table_id}")
        except Exception as e:
            current_app.logger.error(
                f"Error initializing engine for table {table_id}: {e}"
            )
            abort(500, "Could not initialize game engine")

    seated_players = BlackjackTableSeat.query.filter_by(table_id=table_id).all()

    return render_template(
        "blackjack_table_improved.html",
        table_id=table_id,
        table=table,
        seated_players=seated_players,
        user=current_user,
    )


# ============================================================================
# STATE ENDPOINT
# ============================================================================

@blackjack_bp.route("/api/table/<int:table_id>/state", methods=["GET"])
@login_required
def get_table_state(table_id):
    """
    Get current table state from in-memory engine.

    The engine's get_state() should already return:
      - phase
      - current_player_seat
      - button_seat
      - per-player info with:
        seat, player_id, username, stack, normal_circle, escrow_circle,
        is_button, is_folded, escrow_locked, exposed_card
      - normal_pot, escrow_pot, etc.
    """
    try:
        if table_id not in TABLES:
            return jsonify({"error": "Table not found in engine"}), 404

        engine = TABLES[table_id]
        state = engine.get_state()  # use engine's own JSON-safe view

        # Attach current user id so frontend can detect "me"
        state["current_user_id"] = current_user.id

        return jsonify(state)
    except Exception as e:
        current_app.logger.error(f"Error in get_table_state: {e}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500


# ============================================================================
# SEATING / READY
# ============================================================================

@blackjack_bp.route("/api/join_seat/<int:table_id>/<int:seat_number>", methods=["POST"])
@login_required
def join_seat(table_id, seat_number):
    """Join a specific seat at a table"""
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found"}), 404

    if seat_number < 0 or seat_number >= table.maxseats:
        return jsonify({"error": "Invalid seat number"}), 400

    data = request.get_json() or {}
    buy_in_antes = data.get("buy_in_antes", 200)

    if buy_in_antes < 100 or buy_in_antes > 500:
        return jsonify({"error": "Buy-in must be between 100 and 500 antes"}), 400

    seat = BlackjackTableSeat.query.filter_by(
        tableid=table_id, seatnumber=seat_number
    ).first()
    if not seat:
        return jsonify({"error": "Seat not found"}), 404

    if seat.userid is not None:
        return jsonify({"error": "Seat already occupied"}), 409

    existing_seat = BlackjackTableSeat.query.filter_by(
        tableid=table_id, userid=current_user.id
    ).first()
    if existing_seat:
        return jsonify({"error": "You are already seated at this table"}), 409

    seat.userid = current_user.id
    seat.joinedat = datetime.utcnow()

    buy_in_chips = buy_in_antes * table.antevalue
    seat.buyinantes = buy_in_antes

    db.session.commit()

    if table_id not in PLAYER_READY_STATUS:
        PLAYER_READY_STATUS[table_id] = {}
    PLAYER_READY_STATUS[table_id] = {}

    return jsonify(
        {
            "status": "seated",
            "table_id": table_id,
            "seat_number": seat_number,
            "user_id": current_user.id,
            "username": current_user.username,
            "buy_in_antes": buy_in_antes,
            "buy_in_chips": buy_in_chips,
            "seat_count": table.seatcount,
        }
    )


@blackjack_bp.route("/api/table/<int:table_id>/player_ready", methods=["POST"])
@login_required
def player_ready(table_id):
    """Mark a player as ready to start the hand"""
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found"}), 404

    seat = BlackjackTableSeat.query.filter_by(
        tableid=table_id, userid=current_user.id
    ).first()
    if not seat:
        return jsonify({"error": "You are not seated at this table"}), 403

    if table_id not in PLAYER_READY_STATUS:
        PLAYER_READY_STATUS[table_id] = {}
    PLAYER_READY_STATUS[table_id][current_user.id] = True

    seated_seats = (
        BlackjackTableSeat.query.filter_by(tableid=table_id)
        .filter(BlackjackTableSeat.userid.isnot(None))
        .all()
    )

    all_ready = all(
        PLAYER_READY_STATUS[table_id].get(s.userid, False) for s in seated_seats
    )

    button_assigned = False
    hand_started = False

    if all_ready and len(seated_seats) >= 2 and table_id in TABLES:
        table = BlackjackTable.query.filter_by(id=table_id).first()
        if table and table.markedforclose:
            table.isopen = False
            db.session.commit()
            current_app.logger.info(
                f"Table {table_id} closed before starting new hand (marked for close)"
            )
            return jsonify(
                {
                    "status": "ready",
                    "table_id": table_id,
                    "user_id": current_user.id,
                    "table_closed": True,
                    "message": "Table has been closed by admin after the hand finished",
                }
            )

        try:
            engine = TABLES[table_id]
            if engine.game_state is None or engine.game_state.phase == GamePhase.HAND_END:
                table = BlackjackTable.query.filter_by(id=table_id).first()
                player_list = [
                    (s.seatnumber, s.userid, s.user.username) for s in seated_seats
                ]
                initial_stack = (
                    seated_seats[0].buyinantes * table.antevalue
                    if seated_seats and seated_seats[0].buyinantes
                    else 1000
                )
                engine.create_table(
                    player_list, initial_stack=initial_stack, ante_value=table.antevalue
                )

                if engine.game_state and engine.game_state.players:
                    for i, player in enumerate(engine.game_state.players):
                        if i < len(seated_seats):
                            buy_in_chips = seated_seats[i].buyinantes * table.antevalue
                            player.stack = buy_in_chips

                import random

                button_seat = random.randint(0, len(player_list) - 1)
                engine.game_state.buttonseat = button_seat

                engine.setup_hand()
                hand_started = True
                button_assigned = True

                current_app.logger.info(
                    f"Button assigned to seat {button_seat} at table {table_id}, hand started"
                )

                PLAYER_READY_STATUS[table_id] = {}
        except Exception as e:
            current_app.logger.error(
                f"Error assigning button and starting hand: {e}"
            )
            return jsonify({"error": str(e)}), 400

    return jsonify(
        {
            "status": "ready",
            "table_id": table_id,
            "user_id": current_user.id,
            "button_assigned": button_assigned,
            "hand_started": hand_started,
            "all_ready": all_ready,
            "ready_count": len(
                [u for u, r in PLAYER_READY_STATUS[table_id].items() if r]
            ),
            "seated_count": len(seated_seats),
            "game_state": TABLES[table_id].get_state()
            if hand_started and table_id in TABLES
            else None,
        }
    )


@blackjack_bp.route("/api/leave_seat/<int:table_id>", methods=["POST"])
@login_required
def leave_seat(table_id):
    """Leave a table"""
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found"}), 404

    seat = BlackjackTableSeat.query.filter_by(
        tableid=table_id, userid=current_user.id
    ).first()
    if not seat:
        return jsonify({"error": "You are not seated at this table"}), 404

    seat.userid = None
    seat.joinedat = None
    db.session.commit()

    return jsonify({"status": "left", "table_id": table_id})


# ============================================================================
# HAND CONTROL / ACTIONS
# ============================================================================

@blackjack_bp.route("/api/table/<int:table_id>/start_hand", methods=["POST"])
@login_required
def start_hand(table_id):
    """Start a new hand at the table (with seated players from database)"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    seated_seats = (
        BlackjackTableSeat.query.filter_by(tableid=table_id)
        .filter(BlackjackTableSeat.userid.isnot(None))
        .all()
    )
    if len(seated_seats) < 2:
        return jsonify({"error": "Need at least 2 players to start"}), 400

    table = BlackjackTable.query.filter_by(id=table_id).first()
    player_list = [
        (seat.seatnumber, seat.userid, seat.user.username) for seat in seated_seats
    ]

    engine = TABLES[table_id]

    try:
        initial_stack = (
            seated_seats[0].buyinantes * table.antevalue
            if seated_seats[0].buyinantes
            else 1000
        )

        engine.create_table(
            player_list, initial_stack=initial_stack, ante_value=table.antevalue
        )

        if engine.game_state and engine.game_state.players:
            for i, player in enumerate(engine.game_state.players):
                if i < len(seated_seats):
                    buy_in_chips = seated_seats[i].buyinantes * table.antevalue
                    player.stack = buy_in_chips

        engine.setup_hand()
        return jsonify({"message": "Hand started", "state": engine.get_state()})
    except Exception as e:
        current_app.logger.error(f"Error starting hand: {e}")
        return jsonify({"error": str(e)}), 400


@blackjack_bp.route("/api/table/<int:table_id>/legal_actions/<int:seat>", methods=["GET"])
@login_required
def get_legal_actions_endpoint(table_id, seat):
    """Get legal actions for a player"""
    try:
        if table_id not in TABLES:
            return jsonify({"error": "Table not found"}), 404

        engine = TABLES[table_id]
        actions = engine.get_legal_actions(seat)

        return jsonify({"actions": [a.name for a in actions]})
    except Exception as e:
        current_app.logger.error(f"Error getting legal actions: {e}")
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

    player = next((p for p in engine.game_state.players if p.seat == seat), None)
    if not player or player.playerid != current_user.id:
        return jsonify({"error": "Not your seat"}), 403

    try:
        action = ActionType[action_name.upper()]

        card_index = data.get("card_index")
        if card_index is not None:
            card_index = int(card_index)

        engine.player_action(seat, action, amount, card_index=card_index)

        return jsonify({"state": engine.get_state()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": f"Unknown action: {action_name}"}), 400


@blackjack_bp.route("/api/table/<int:table_id>/advance_phase", methods=["POST"])
@login_required
def advance_phase(table_id):
    """Advance to next phase (used mainly when hand is over)"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    engine = TABLES[table_id]

    try:
        if engine.game_state.phase == GamePhase.HAND_END:
            if table_id in PLAYER_READY_STATUS:
                PLAYER_READY_STATUS[table_id] = {}

            table = BlackjackTable.query.filter_by(id=table_id).first()
            if table and table.markedforclose:
                table.isopen = False
                db.session.commit()
                current_app.logger.info(
                    f"Table {table_id} closed after hand (marked for close)"
                )

        return jsonify({"state": engine.get_state()})
    except Exception as e:
        current_app.logger.error(f"Error advancing phase: {e}")
        return jsonify({"error": str(e)}), 400
