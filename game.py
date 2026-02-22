from flask import (
    Blueprint, request, jsonify, abort,
    session, render_template, redirect, url_for
)
from flask_login import login_required, current_user
from extensions import db
from models import Match, User, JackpotPool
from engine import (
    GAME_MODES,
    init_game_state,
    do_card_draw,
    make_choice,
    enter_turn,
    place_bets,
    handle_insurance,
    player_action,
    dealer_action,
    assign_joker_values,
    assign_dealer_joker_values,
    next_round_or_end_turn,
    end_turn,
    apply_timeout,
    get_client_state,
)

game_bp = Blueprint("game", __name__, url_prefix="/game")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _get_user_or_401() -> User:
    # Flask-Login source of truth
    if not current_user.is_authenticated:
        abort(401)
    return current_user

def _get_match_or_404(match_id: int) -> Match:
    match = db.session.get(Match, match_id)
    if not match:
        abort(404, "Match not found")
    return match

def _get_user_player_num(match: Match) -> int:
    if not current_user.is_authenticated:
        abort(401, "Not authenticated")

    user_id = current_user.id

    if user_id == match.player1_id:
        return 1
    if user_id == match.player2_id:
        return 2
    abort(403, "Not a participant in this match")

def _get_jackpot_pools_for_lobby():
    # Lobby template expects jackpot_pools.standard / jackpot_pools.joker
    standard = JackpotPool.get_active_pool("standard")
    joker = JackpotPool.get_active_pool("joker")
    return {"standard": standard, "joker": joker}


# -------------------------------------------------------------------
# PAGES
# -------------------------------------------------------------------

@game_bp.route("/lobby", methods=["GET"])
@login_required
def lobby():
    user = _get_user_or_401()

    # Your active matches (active and user is player1 or player2)
    my_active = (
        Match.query
        .filter(Match.status_code == Match.MATCH_STATUS["active"])
        .filter((Match.player1_id == user.id) | (Match.player2_id == user.id))
        .order_by(Match.id.desc())
        .all()
    )

    # Waiting matches (waiting status)
    waiting = (
        Match.query
        .filter(Match.status_code == Match.MATCH_STATUS["waiting"])
        .order_by(Match.id.desc())
        .all()
    )

    jackpot_pools = _get_jackpot_pools_for_lobby()

    return render_template(
        "lobby.html",
        user=user,
        game_modes=GAME_MODES,
        my_active=my_active,
        waiting=waiting,
        jackpot_pools=jackpot_pools,
    )


@game_bp.route("/watch", methods=["GET"])
@login_required
def watch():
    # watch.html expects top_lobby and tournament_display
    top_lobby = (
        Match.query
        .filter(Match.status_code == Match.MATCH_STATUS["active"])
        .filter(Match.is_spectatable.is_(True))
        .order_by(Match.id.desc())
        .limit(25)
        .all()
    )

    # Your repo has tournament templates, but building full tournament_display
    # depends on tournament logic; keep safe default to avoid crashes.
    tournament_display = []

    return render_template(
        "watch.html",
        top_lobby=top_lobby,
        tournament_display=tournament_display,
    )


@game_bp.route("/play/<int:match_id>", methods=["GET"])
@login_required
def play(match_id):
    user = _get_user_or_401()
    match = _get_match_or_404(match_id)

    # must be a participant
    player_num = _get_user_player_num(match)

    p1 = match.player1
    p2 = match.player2

    return render_template(
        "game.html",
        match=match,
        p1=p1,
        p2=p2,
        player_num=player_num,
        game_modes=GAME_MODES,
    )


@game_bp.route("/spectate/<int:match_id>", methods=["GET"])
@login_required
def spectate(match_id):
    match = _get_match_or_404(match_id)
    if not match.is_spectatable:
        abort(403)

    p1 = match.player1
    p2 = match.player2

    return render_template(
        "spectate.html",
        match=match,
        p1=p1,
        p2=p2,
    )


# -------------------------------------------------------------------
# LOBBY ACTIONS (used by lobby.html forms)
# -------------------------------------------------------------------

@game_bp.route("/create_match", methods=["POST"])
@login_required
def create_match():
    user = _get_user_or_401()

    game_mode = request.form.get("game_mode", "classic")
    stake_raw = request.form.get("stake", "0")

    try:
        stake = int(stake_raw)
    except ValueError:
        abort(400, "Invalid stake")

    if stake < 10:
        abort(400, "Minimum stake is 10")

    if stake > int(user.coins):
        abort(400, "Not enough coins")

    # lock stake immediately (refund on cancel; payout on finish)
    user.coins = int(user.coins) - stake

    match = Match(
        player1_id=user.id,
        player2_id=None,
        stake=stake,
    )
    match.game_mode = game_mode
    match.status = "waiting"

    db.session.add(match)
    db.session.commit()

    return redirect(url_for("game.lobby"))


@game_bp.route("/cancel_match/<int:match_id>", methods=["POST"])
@login_required
def cancel_match(match_id):
    user = _get_user_or_401()
    match = _get_match_or_404(match_id)

    if match.player1_id != user.id:
        abort(403)
    if match.status != "waiting":
        abort(400, "Only waiting matches can be cancelled")
    if match.player2_id is not None:
        abort(400, "Cannot cancel after someone joined")

    # refund creator stake
    user.coins = int(user.coins) + int(match.stake)

    db.session.delete(match)
    db.session.commit()

    return redirect(url_for("game.lobby"))


@game_bp.route("/join_match/<int:match_id>", methods=["POST"])
@login_required
def join_match(match_id):
    # Flask-Login authenticated user
    if not current_user.is_authenticated:
        abort(401)

    user = current_user
    match = _get_match_or_404(match_id)

    # Must be waiting
    if match.status != "waiting":
        abort(400, "Match is not joinable")

    # Already has opponent
    if match.player2_id is not None:
        abort(400, "Match already has an opponent")

    # Cannot join your own match
    if match.player1_id == user.id:
        abort(400, "You cannot join your own match")

    # Ensure sufficient balance
    if int(user.coins) < int(match.stake):
        abort(400, "Not enough coins to join")

    # Lock joiner stake
    user.coins = int(user.coins) - int(match.stake)

    # Activate match
    match.player2_id = user.id
    match.status = "active"

    # Initialize SQL game state BEFORE commit
    init_game_state(match)

    # Single atomic commit
    db.session.commit()

    return redirect(url_for("game.play", match_id=match.id))


@game_bp.route("/forfeit_match/<int:match_id>", methods=["POST"])
@login_required
def forfeit_match(match_id):
    user = _get_user_or_401()
    match = _get_match_or_404(match_id)

    if user.id not in (match.player1_id, match.player2_id):
        abort(403)
    if match.status == "finished":
        return redirect(url_for("game.lobby"))

    # opponent wins
    winner_id = match.player2_id if user.id == match.player1_id else match.player1_id
    match.winner_id = winner_id
    match.status = "finished"

    # payout: 2*stake to winner (simple)
    winner = db.session.get(User, winner_id)
    if winner:
        winner.coins = int(winner.coins) + (int(match.stake) * 2)

    db.session.commit()
    return redirect(url_for("game.lobby"))


# -------------------------------------------------------------------
# API ROUTES (used by game.html JS)
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/start", methods=["POST"])
@login_required
def start_game(match_id):
    match = _get_match_or_404(match_id)
    _ = _get_user_player_num(match)

    if match.status != "active":
        return jsonify({"error": "Match is not active"}), 400

    # If state already exists, init_game_state will wipe+rebuild; avoid double start.
    # So only init if MatchState missing.
    from models import MatchState
    ms = MatchState.query.filter_by(match_id=match.id).first()
    if not ms:
        init_game_state(match)

    payload = get_client_state(match, _get_user_player_num(match))
    return jsonify(payload)


@game_bp.route("/<int:match_id>/draw", methods=["POST"])
@login_required
def draw_card(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    do_card_draw(match)
    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/choice", methods=["POST"])
@login_required
def choice(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    goes_first = bool(data.get("goes_first"))
    make_choice(match, goes_first)

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/bet", methods=["POST"])
@login_required
def bet(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    bets = data.get("bets", [])

    try:
        place_bets(match, bets)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/insurance", methods=["POST"])
@login_required
def insurance(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    decisions = data.get("decisions", [])
    handle_insurance(match, decisions)

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/action", methods=["POST"])
@login_required
def action(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    action_type = data.get("action")

    try:
        player_action(match, action_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/dealer_action", methods=["POST"])
@login_required
def dealer_action_route(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    action_type = data.get("action")

    try:
        dealer_action(match, action_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/joker", methods=["POST"])
@login_required
def assign_joker(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    values = data.get("values", [])
    assign_joker_values(match, values)

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/dealer_joker", methods=["POST"])
@login_required
def assign_dealer_joker(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json() or {}
    values = data.get("values", [])
    assign_dealer_joker_values(match, values)

    return jsonify(get_client_state(match, user_num))


@game_bp.route("/<int:match_id>/next", methods=["POST"])
@login_required
def next_round(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    ended = next_round_or_end_turn(match)

    payload = get_client_state(match, user_num)
    payload["turn_ended"] = ended
    return jsonify(payload)


@game_bp.route("/<int:match_id>/end_turn", methods=["POST"])
@login_required
def end_turn_route(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    ended = end_turn(match)

    payload = get_client_state(match, user_num)
    payload["match_over"] = ended
    return jsonify(payload)


@game_bp.route("/<int:match_id>/timeout", methods=["POST"])
@login_required
def timeout(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    changed = apply_timeout(match)

    payload = get_client_state(match, user_num)
    payload["timeout_applied"] = changed
    return jsonify(payload)


@game_bp.route('/<int:match_id>/state')
@login_required
def state(match_id):
    match = Match.query.get_or_404(match_id)

    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Not part of this match"}), 403

    player_num = 1 if match.player1_id == current_user.id else 2

    # Determine turn ownership
    is_my_turn = False
    if match.phase == "CHOICE":
        is_my_turn = (match.chooser == player_num)
    elif match.phase == "WAITING_BETS":
        is_my_turn = True
    elif match.phase == "PLAYER_TURN":
        is_my_turn = match.current_player_role == player_num
    elif match.phase == "DEALER_TURN":
        is_my_turn = match.current_dealer_role == player_num

    state = {
        "phase": match.phase,
        "chooser": match.chooser,
        "choice_made": match.choice_made,
        "current_turn": match.current_turn,
        "total_turns": match.total_turns,
        "game_mode": match.game_mode,
        "is_heads_up": match.is_heads_up,
        "match_over": match.match_over,
        "match_result": match.match_result,
        "timer_remaining": match.timer_remaining,
        "is_my_turn": is_my_turn,
        "i_am_dealer": match.current_dealer_role == player_num,
        "chips": match.player1_chips if player_num == 1 else match.player2_chips,
    }

    # Draw phase info
    if match.phase in ["CARD_DRAW", "CHOICE"]:
        state.update({
            "draw_cards": match.draw_cards,
            "draw_winner": match.draw_winner,
            "draw_timestamp": match.draw_timestamp,
        })

    # Round data (if exists)
    if match.round_data:
        state["round"] = match.round_data

    return jsonify(state)
