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
    GameEngine,
    GamePhase,
    ActionType,
)

# Simple in-memory table store (for demo; in production use DB)
TABLES = {}  # table_id -> GameEngine instance
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
    num_seats = int(data.get("num_seats", 5))

    if num_seats < 2 or num_seats > 5:
        return jsonify({"error": "Table must have 2-5 seats"}), 400

    TABLE_COUNTER += 1
    table_id = TABLE_COUNTER

    # Initialize with current user + AI/empty seats
    players = [(current_user.id, current_user.username)]
    # Add empty seats
    for i in range(1, num_seats):
        players.append((0, f"Empty Seat {i}"))

    engine = GameEngine(seed=table_id)  # Deterministic seed
    engine.create_table(players, initial_stack=1000)

    TABLES[table_id] = engine

    return jsonify({
        "table_id": table_id,
        "message": "Table created",
    })


@blackjack_bp.route("/table/<int:table_id>", methods=["GET"])
@login_required
def view_table(table_id):
    """View a specific table (with lazy initialization)"""
    # Ensure table exists in database
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        abort(404, "Table not found")

    # Lazy initialize engine if not already done
    if table_id not in TABLES:
        try:
            engine = GameEngine(seed=table_id)
            TABLES[table_id] = engine
            current_app.logger.info(f"Game engine initialized for table {table_id}")
        except Exception as e:
            current_app.logger.error(f"Error initializing engine for table {table_id}: {e}")
            abort(500, "Could not initialize game engine")

    # Get seated players from database
    seated_players = BlackjackTableSeat.query.filter_by(table_id=table_id).all()

    return render_template(
        "blackjack_table_improved.html",
        table_id=table_id,
        table=table,
        seated_players=seated_players,
        user=current_user,
    )


@blackjack_bp.route("/api/table/<int:table_id>/state", methods=["GET"])
@login_required
def get_table_state(table_id):
    """Get current table state with seated players from database"""
    try:
        if table_id not in TABLES:
            return jsonify({"error": "Table not found in engine"}), 404

        # Load seated players from database
        table = BlackjackTable.query.filter_by(id=table_id).first()
        if not table:
            return jsonify({"error": "Table not found in database"}), 404

        seated_seats = BlackjackTableSeat.query.filter_by(table_id=table_id).all()
        engine = TABLES[table_id]
        game_state = engine.get_state()

        # Build seated_players with card information
        table = BlackjackTable.query.filter_by(id=table_id).first()
        seated_players = []
        for seat in seated_seats:
            if seat.user_id is not None:
                # Use buy-in amount as initial stack, or get from game state
                initial_stack = (seat.buy_in_antes * table.ante_value) if seat.buy_in_antes and table else 1000

                player_info = {
                    "seat": seat.seat_number,
                    "username": seat.user.username if seat.user else None,
                    "user_id": seat.user_id,
                    "joined_at": seat.joined_at.isoformat() if seat.joined_at else None,
                    "stack": initial_stack,
                    "card1": None,
                    "card2": None,
                }

                # Try to get card information from game state
                if game_state and game_state.get("players"):
                    for player in game_state.get("players", []):
                        if player.get("seat") == seat.seat_number:
                            player_info["stack"] = player.get("stack", initial_stack)
                            cards = player.get("cards", [])
                            player_info["card1"] = cards[0] if len(cards) > 0 else ""
                            player_info["card2"] = cards[1] if len(cards) > 1 else ""
                            player_info["normal_circle"] = player.get("normal_circle", 0)
                            player_info["escrow_circle"] = player.get("escrow_circle", 0)
                            player_info["is_button"] = player.get("is_button", False)
                            break

                seated_players.append(player_info)

        # Get ready player count
        ready_count = len(PLAYER_READY_STATUS.get(table_id, {}))
        seated_count = len(seated_players)

        # Merge database seating with game engine state
        return jsonify({
            "phase": game_state.get("phase", "setup"),
            "current_player_seat": game_state.get("current_player_seat"),
            "button_seat": game_state.get("button_seat"),
            "current_user_id": current_user.id,  # Pass current user's ID so frontend knows whose turn it is
            "seated_players": seated_players,
            "game_state": game_state,
            "normal_pot": game_state.get("normal_pot", 0),
            "escrow_pot": game_state.get("escrow_pot", 0),
            "ready_count": ready_count,
            "seated_count": seated_count,
        })
    except Exception as e:
        current_app.logger.error(f"Error in get_table_state: {e}", exc_info=True)
        return jsonify({"error": f"Server error: {str(e)}"}), 500


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

    # Get buy-in amount in antes from request
    data = request.get_json() or {}
    buy_in_antes = data.get("buy_in_antes", 200)

    # Validate buy-in amount
    if buy_in_antes < 100 or buy_in_antes > 500:
        return jsonify({"error": "Buy-in must be between 100 and 500 antes"}), 400

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

    # Store buy-in amount in antes (convert to chips for internal storage)
    buy_in_chips = buy_in_antes * table.ante_value
    seat.buy_in_antes = buy_in_antes

    db.session.commit()

    # Initialize ready status for this table if needed
    if table_id not in PLAYER_READY_STATUS:
        PLAYER_READY_STATUS[table_id] = {}

    # Reset all ready statuses when new player joins (mid-game scenario)
    PLAYER_READY_STATUS[table_id] = {}

    # Return seat info
    return jsonify({
        "status": "seated",
        "table_id": table_id,
        "seat_number": seat_number,
        "user_id": current_user.id,
        "username": current_user.username,
        "buy_in_antes": buy_in_antes,
        "buy_in_chips": buy_in_chips,
        "seat_count": table.seat_count
    })


@blackjack_bp.route("/api/table/<int:table_id>/player_ready", methods=["POST"])
@login_required
def player_ready(table_id):
    """Mark a player as ready to start the hand"""
    # Check table exists
    table = BlackjackTable.query.filter_by(id=table_id).first()
    if not table:
        return jsonify({"error": "Table not found"}), 404

    # Check user is seated
    seat = BlackjackTableSeat.query.filter_by(
        table_id=table_id,
        user_id=current_user.id
    ).first()

    if not seat:
        return jsonify({"error": "You are not seated at this table"}), 403

    # Mark player as ready
    if table_id not in PLAYER_READY_STATUS:
        PLAYER_READY_STATUS[table_id] = {}

    PLAYER_READY_STATUS[table_id][current_user.id] = True

    # Get all seated players
    seated_seats = BlackjackTableSeat.query.filter_by(table_id=table_id).filter(
        BlackjackTableSeat.user_id.isnot(None)
    ).all()

    # Check if all seated players are ready
    all_ready = all(
        PLAYER_READY_STATUS[table_id].get(s.user_id, False)
        for s in seated_seats
    )

    button_assigned = False
    hand_started = False
    if all_ready and len(seated_seats) >= 2 and table_id in TABLES:
        # Check if table is marked for closing - if so, close it instead of starting new hand
        table = BlackjackTable.query.filter_by(id=table_id).first()
        if table and table.marked_for_close:
            table.is_open = False
            db.session.commit()
            current_app.logger.info(f"Table {table_id} closed before starting new hand (marked for close)")
            return jsonify({
                "status": "ready",
                "table_id": table_id,
                "user_id": current_user.id,
                "table_closed": True,
                "message": "Table has been closed by admin after the hand finished"
            })

        # All players ready and at least 2 players - initialize game, assign button, and start hand
        try:
            engine = TABLES[table_id]
            if engine.game_state is None or engine.game_state.phase == GamePhase.HAND_OVER:
                # Get table info for ante value
                table = BlackjackTable.query.filter_by(id=table_id).first()

                # Create player list from database seating with buy-in amounts
                player_list = [
                    (s.user_id, s.user.username)
                    for s in seated_seats
                ]

                # Use first player's buy-in as initial stack (or default to 1000 if not set)
                initial_stack = seated_seats[0].buy_in_antes * table.ante_value if seated_seats and seated_seats[0].buy_in_antes else 1000
                engine.create_table(player_list, initial_stack=initial_stack)

                # Set individual stacks based on buy-in amounts
                if engine.game_state and engine.game_state.players:
                    for i, player in enumerate(engine.game_state.players):
                        if i < len(seated_seats):
                            buy_in_chips = seated_seats[i].buy_in_antes * table.ante_value
                            player.stack = buy_in_chips

                # Randomly select button using RNG
                import random
                button_seat = random.randint(0, len(player_list) - 1)
                engine.game_state.button_seat = button_seat

                # Automatically start the hand
                engine.setup_hand()
                hand_started = True
                button_assigned = True

                current_app.logger.info(f"Button assigned to seat {button_seat} at table {table_id}, hand started")

                # Reset ready status for next hand
                PLAYER_READY_STATUS[table_id] = {}
        except Exception as e:
            current_app.logger.error(f"Error assigning button and starting hand: {e}")
            return jsonify({"error": str(e)}), 400

    return jsonify({
        "status": "ready",
        "table_id": table_id,
        "user_id": current_user.id,
        "button_assigned": button_assigned,
        "hand_started": hand_started,
        "all_ready": all_ready,
        "ready_count": len([u for u, r in PLAYER_READY_STATUS[table_id].items() if r]),
        "seated_count": len(seated_seats),
        "game_state": TABLES[table_id].get_state() if hand_started and table_id in TABLES else None
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
    """Start a new hand at the table (with seated players from database)"""
    if table_id not in TABLES:
        return jsonify({"error": "Table not found"}), 404

    # Load seated players from database
    seated_seats = BlackjackTableSeat.query.filter_by(table_id=table_id).filter(
        BlackjackTableSeat.user_id.isnot(None)
    ).all()

    if len(seated_seats) < 2:
        return jsonify({"error": "Need at least 2 players to start"}), 400

    # Get table info for ante value
    table = BlackjackTable.query.filter_by(id=table_id).first()

    # Create player list from database seating
    player_list = [
        (seat.user_id, seat.user.username)
        for seat in seated_seats
    ]

    engine = TABLES[table_id]

    try:
        # Use first player's buy-in as initial stack (or default to 1000)
        initial_stack = seated_seats[0].buy_in_antes * table.ante_value if seated_seats[0].buy_in_antes else 1000

        # Initialize game with seated players
        engine.create_table(player_list, initial_stack=initial_stack)

        # Set individual stacks based on buy-in amounts
        if engine.game_state and engine.game_state.players:
            for i, player in enumerate(engine.game_state.players):
                if i < len(seated_seats):
                    buy_in_chips = seated_seats[i].buy_in_antes * table.ante_value
                    player.stack = buy_in_chips

        # Start the hand
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

        return jsonify({"actions": actions})
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

    # Get current player
    player = next((p for p in engine.game_state.players if p.seat == seat), None)
    if not player or player.user_id != current_user.id:
        return jsonify({"error": "Not your seat"}), 403

    try:
        # Import here to avoid circular dependency
        from blackjack_game_engine import ActionType
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
        # If hand is over, prepare next hand
        if engine.game_state.phase == GamePhase.HAND_END:
            # Reset ready status
            if table_id in PLAYER_READY_STATUS:
                PLAYER_READY_STATUS[table_id] = {}

            # Check if table is marked for closing and close it
            table = BlackjackTable.query.filter_by(id=table_id).first()
            if table and table.marked_for_close:
                table.is_open = False
                db.session.commit()
                current_app.logger.info(f"Table {table_id} closed after hand (marked for close)")

        return jsonify({"state": engine.get_state()})
    except Exception as e:
        current_app.logger.error(f"Error advancing phase: {e}")
        return jsonify({"error": str(e)}), 400
