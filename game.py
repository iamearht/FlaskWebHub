from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Match
from auth import login_required, get_current_user
from engine import (
    init_game_state, start_turn, place_bets, handle_insurance,
    player_action, next_round_or_end_turn, get_client_state
)

game_bp = Blueprint('game', __name__)

@game_bp.route('/lobby')
@login_required
def lobby():
    user = get_current_user()
    waiting = Match.query.filter_by(status='waiting').filter(Match.player1_id != user.id).all()
    my_matches = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status.in_(['waiting', 'active'])
    ).all()
    history = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status == 'finished'
    ).order_by(Match.created_at.desc()).limit(10).all()
    return render_template('lobby.html', user=user, waiting=waiting, my_matches=my_matches, history=history)

@game_bp.route('/create_match', methods=['POST'])
@login_required
def create_match():
    user = get_current_user()
    try:
        stake = int(request.form.get('stake', 0))
    except (ValueError, TypeError):
        flash('Invalid stake amount.', 'error')
        return redirect(url_for('game.lobby'))

    if stake < 10:
        flash('Minimum stake is 10 coins.', 'error')
        return redirect(url_for('game.lobby'))
    if stake > user.coins:
        flash('Not enough coins.', 'error')
        return redirect(url_for('game.lobby'))

    user.coins -= stake
    match = Match(player1_id=user.id, stake=stake, status='waiting', game_state=None)
    db.session.add(match)
    db.session.commit()
    flash(f'Match created with {stake} coin stake.', 'success')
    return redirect(url_for('game.lobby'))

@game_bp.route('/join_match/<int:match_id>', methods=['POST'])
@login_required
def join_match(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'waiting':
        flash('Match is no longer available.', 'error')
        return redirect(url_for('game.lobby'))
    if match.player1_id == user.id:
        flash('Cannot join your own match.', 'error')
        return redirect(url_for('game.lobby'))
    if match.stake > user.coins:
        flash('Not enough coins to match the stake.', 'error')
        return redirect(url_for('game.lobby'))

    user.coins -= match.stake
    match.player2_id = user.id
    match.status = 'active'
    match.game_state = init_game_state()
    db.session.commit()
    return redirect(url_for('game.play', match_id=match.id))

@game_bp.route('/match/<int:match_id>')
@login_required
def play(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if user.id not in (match.player1_id, match.player2_id):
        flash('Not your match.', 'error')
        return redirect(url_for('game.lobby'))

    if match.status == 'waiting':
        return render_template('waiting.html', match=match, user=user)

    if match.status == 'finished':
        state = match.game_state
        player_num = 1 if user.id == match.player1_id else 2
        cs = get_client_state(state, player_num)
        p1 = User.query.get(match.player1_id)
        p2 = User.query.get(match.player2_id)
        return render_template('match_result.html', match=match, user=user, cs=cs, p1=p1, p2=p2)

    player_num = 1 if user.id == match.player1_id else 2
    state = match.game_state
    cs = get_client_state(state, player_num)
    p1 = User.query.get(match.player1_id)
    p2 = User.query.get(match.player2_id)
    return render_template('game.html', match=match, user=user, cs=cs, player_num=player_num, p1=p1, p2=p2)

@game_bp.route('/api/match/<int:match_id>/state')
@login_required
def api_state(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if user.id not in (match.player1_id, match.player2_id):
        return jsonify({'error': 'Not your match'}), 403
    player_num = 1 if user.id == match.player1_id else 2
    cs = get_client_state(match.game_state, player_num)
    user_obj = User.query.get(user.id)
    cs['user_coins'] = user_obj.coins
    cs['stake'] = match.stake
    cs['status'] = match.status
    return jsonify(cs)

@game_bp.route('/api/match/<int:match_id>/start_turn', methods=['POST'])
@login_required
def api_start_turn(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400
    if user.id not in (match.player1_id, match.player2_id):
        return jsonify({'error': 'Not your match'}), 403

    state = match.game_state
    if state['phase'] != 'TURN_START':
        return jsonify({'error': 'Not in turn start phase'}), 400

    state = start_turn(state)
    match.game_state = state
    db.session.commit()

    player_num = 1 if user.id == match.player1_id else 2
    return jsonify(get_client_state(state, player_num))

@game_bp.route('/api/match/<int:match_id>/bet', methods=['POST'])
@login_required
def api_bet(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = 1 if user.id == match.player1_id else 2
    state = match.game_state
    turn_info = state['turns_order'][state['current_turn']]
    if turn_info['player_role'] != player_num:
        return jsonify({'error': 'Not your turn'}), 403

    data = request.get_json()
    bets = data.get('bets', [])

    state, err = place_bets(state, bets)
    if err:
        return jsonify({'error': err}), 400

    match.game_state = state
    db.session.commit()
    return jsonify(get_client_state(state, player_num))

@game_bp.route('/api/match/<int:match_id>/insurance', methods=['POST'])
@login_required
def api_insurance(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = 1 if user.id == match.player1_id else 2
    state = match.game_state
    turn_info = state['turns_order'][state['current_turn']]
    if turn_info['player_role'] != player_num:
        return jsonify({'error': 'Not your turn'}), 403

    data = request.get_json()
    take = data.get('take', False)

    state, err = handle_insurance(state, take)
    if err:
        return jsonify({'error': err}), 400

    match.game_state = state
    db.session.commit()
    return jsonify(get_client_state(state, player_num))

@game_bp.route('/api/match/<int:match_id>/action', methods=['POST'])
@login_required
def api_action(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = 1 if user.id == match.player1_id else 2
    state = match.game_state
    turn_info = state['turns_order'][state['current_turn']]
    if turn_info['player_role'] != player_num:
        return jsonify({'error': 'Not your turn'}), 403

    data = request.get_json()
    action = data.get('action')
    if action not in ('hit', 'stand', 'double', 'split'):
        return jsonify({'error': 'Invalid action'}), 400

    state, err = player_action(state, action)
    if err:
        return jsonify({'error': err}), 400

    match.game_state = state
    db.session.commit()
    return jsonify(get_client_state(state, player_num))

@game_bp.route('/api/match/<int:match_id>/next_round', methods=['POST'])
@login_required
def api_next_round(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = 1 if user.id == match.player1_id else 2
    state = match.game_state

    if state['phase'] != 'ROUND_RESULT':
        return jsonify({'error': 'Not in round result phase'}), 400

    state, match_ended = next_round_or_end_turn(state)

    if match_ended:
        result = state['match_result']
        if result['winner'] == 1:
            p1 = User.query.get(match.player1_id)
            p1.coins += match.stake * 2
            match.winner_id = match.player1_id
        elif result['winner'] == 2:
            p2 = User.query.get(match.player2_id)
            p2.coins += match.stake * 2
            match.winner_id = match.player2_id
        else:
            p1 = User.query.get(match.player1_id)
            p2 = User.query.get(match.player2_id)
            p1.coins += match.stake
            p2.coins += match.stake
            match.winner_id = None

        match.status = 'finished'

    match.game_state = state
    db.session.commit()
    return jsonify(get_client_state(state, player_num))

@game_bp.route('/cancel_match/<int:match_id>', methods=['POST'])
@login_required
def cancel_match(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'waiting' or match.player1_id != user.id:
        flash('Cannot cancel this match.', 'error')
        return redirect(url_for('game.lobby'))
    user.coins += match.stake
    db.session.delete(match)
    db.session.commit()
    flash('Match cancelled. Stake refunded.', 'success')
    return redirect(url_for('game.lobby'))
