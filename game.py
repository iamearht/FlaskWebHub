from flask import Blueprint, request, jsonify, abort, session, render_template, redirect, url_for
from auth import login_required
from extensions import db
from models import Match, User
from engine import (
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
    set_decision_timer,
    clear_decision_timer,
)

game_bp = Blueprint("game", __name__, url_prefix="/game")

# -------------------------------------------------------------------
# Lobby Route
# -------------------------------------------------------------------

@game_bp.route("/lobby", methods=["GET"])
@login_required
def lobby():
    """
    Main game lobby page.
    Required because auth.py redirects to url_for('game.lobby')
    """

    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    user = db.session.get(User, user_id)
    if not user:
        abort(403)

    return render_template("lobby.html", user=user)

# -------------------------------------------------------------------
# Create Match
# -------------------------------------------------------------------

@game_bp.route("/create_match", methods=["POST"])
@login_required
def create_match():
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    # Create new match with current user as player1
    match = Match(
        player1_id=user_id,
        player2_id=None,
        started=False
    )

    db.session.add(match)
    db.session.commit()

    return redirect(url_for("game.lobby"))
# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _get_match_or_404(match_id: int) -> Match:
    match = Match.query.get(match_id)
    if not match:
        abort(404, "Match not found")
    return match


def _get_user_player_num(match: Match) -> int:
    user_id = session.get("user_id")
    if not user_id:
        abort(401, "Not authenticated")

    if user_id == match.player1_id:
        return 1
    if user_id == match.player2_id:
        return 2

    abort(403, "Not a participant in this match")


# -------------------------------------------------------------------
# Start Game
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/start", methods=["POST"])
@login_required
def start_game(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    if match.started:
        return jsonify({"error": "Match already started"}), 400

    match.started = True
    db.session.commit()

    init_game_state(match)

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Draw Card Phase
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/draw", methods=["POST"])
@login_required
def draw_card(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    do_card_draw(match)

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Choice Phase
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/choice", methods=["POST"])
@login_required
def choice(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    goes_first = bool(data.get("goes_first"))

    make_choice(match, goes_first)

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Place Bets
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/bet", methods=["POST"])
@login_required
def bet(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    bets = data.get("bets", [])

    try:
        place_bets(match, bets)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Insurance
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/insurance", methods=["POST"])
@login_required
def insurance(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    decisions = data.get("decisions", [])

    handle_insurance(match, decisions)

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Player Action
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/action", methods=["POST"])
@login_required
def action(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    action_type = data.get("action")

    try:
        player_action(match, action_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Dealer Action (interactive mode)
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/dealer_action", methods=["POST"])
@login_required
def dealer_action_route(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    action_type = data.get("action")

    try:
        dealer_action(match, action_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Assign Joker (Player)
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/joker", methods=["POST"])
@login_required
def assign_joker(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    values = data.get("values", [])

    assign_joker_values(match, values)

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Assign Joker (Dealer)
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/dealer_joker", methods=["POST"])
@login_required
def assign_dealer_joker(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    data = request.get_json()
    values = data.get("values", [])

    assign_dealer_joker_values(match, values)

    payload = get_client_state(match, user_num)
    return jsonify(payload)


# -------------------------------------------------------------------
# Next Round
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/next", methods=["POST"])
@login_required
def next_round(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    ended = next_round_or_end_turn(match)

    payload = get_client_state(match, user_num)
    payload["turn_ended"] = ended
    return jsonify(payload)


# -------------------------------------------------------------------
# End Turn
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/end_turn", methods=["POST"])
@login_required
def end_turn_route(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    ended = end_turn(match)

    payload = get_client_state(match, user_num)
    payload["match_over"] = ended
    return jsonify(payload)


# -------------------------------------------------------------------
# Timeout Handler
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/timeout", methods=["POST"])
@login_required
def timeout(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    changed = apply_timeout(match)

    payload = get_client_state(match, user_num)
    payload["timeout_applied"] = changed
    return jsonify(payload)


# -------------------------------------------------------------------
# State Fetch
# -------------------------------------------------------------------

@game_bp.route("/<int:match_id>/state", methods=["GET"])
@login_required
def state(match_id):
    match = _get_match_or_404(match_id)
    user_num = _get_user_player_num(match)

    payload = get_client_state(match, user_num)
    return jsonify(payload)
