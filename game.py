from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy.orm.attributes import flag_modified
from models import db, User, Match
from auth import login_required, get_current_user
from engine import (
    init_game_state, enter_turn, place_bets, handle_insurance,
    player_action, dealer_action, next_round_or_end_turn, get_client_state,
    check_timeout, apply_timeout, set_decision_timer, clear_decision_timer
)

game_bp = Blueprint('game', __name__)


def _save_match(match):
    flag_modified(match, 'game_state')
    db.session.commit()


def _get_player_num(user, match):
    return 1 if user.id == match.player1_id else 2


def _check_and_handle_timeout(match):
    if not check_timeout(match):
        return False
    state = match.game_state
    state, changed = apply_timeout(state, match)
    if changed:
        match.game_state = state
        _set_timer_for_phase(match, state)
        if state.get('match_over'):
            _settle_match(match, state)
        _save_match(match)
    return changed


def _set_timer_for_phase(match, state):
    phase = state['phase']
    if phase == 'WAITING_BETS':
        set_decision_timer(match, 'BET')
    elif phase == 'INSURANCE':
        set_decision_timer(match, 'INSURANCE')
    elif phase == 'PLAYER_TURN':
        set_decision_timer(match, 'ACTION')
    elif phase == 'DEALER_TURN':
        set_decision_timer(match, 'DEALER')
    elif phase == 'ROUND_RESULT':
        set_decision_timer(match, 'NEXT')
    elif phase in ('TURN_START', 'MATCH_OVER'):
        clear_decision_timer(match)


def _settle_match(match, state):
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
    match = Match(player1_id=user.id, stake=stake, status='waiting')
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
    _save_match(match)
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

    state = match.game_state
    if state and 'turns' not in state:
        match.status = 'finished'
        match.game_state = state
        if match.winner_id is None:
            p1u = User.query.get(match.player1_id)
            p2u = User.query.get(match.player2_id)
            if p1u:
                p1u.coins += match.stake
            if p2u and match.player2_id:
                p2u.coins += match.stake
        _save_match(match)
        flash('This match used an old format and has been closed. Stakes refunded.', 'error')
        return redirect(url_for('game.lobby'))

    if match.status == 'active':
        _check_and_handle_timeout(match)

    player_num = _get_player_num(user, match)
    state = match.game_state
    p1 = User.query.get(match.player1_id)
    p2 = User.query.get(match.player2_id)

    if match.status == 'finished':
        cs = get_client_state(state, player_num, match)
        return render_template('match_result.html', match=match, user=user, cs=cs, p1=p1, p2=p2)

    cs = get_client_state(state, player_num, match)
    return render_template('game.html', match=match, user=user, cs=cs, player_num=player_num, p1=p1, p2=p2)


@game_bp.route('/api/match/<int:match_id>/state')
@login_required
def api_state(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if user.id not in (match.player1_id, match.player2_id):
        return jsonify({'error': 'Not your match'}), 403
    state = match.game_state
    if state and 'turns' not in state:
        return jsonify({'error': 'Old match format', 'status': 'finished'}), 400
    if match.status == 'active':
        _check_and_handle_timeout(match)
    player_num = _get_player_num(user, match)
    cs = get_client_state(match.game_state, player_num, match)
    cs['user_coins'] = User.query.get(user.id).coins
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

    _check_and_handle_timeout(match)
    state = match.game_state

    if state['phase'] != 'TURN_START':
        return jsonify({'error': 'Not in turn start phase'}), 400

    state = enter_turn(state)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    player_num = _get_player_num(user, match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/bet', methods=['POST'])
@login_required
def api_bet(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = _get_player_num(user, match)
    _check_and_handle_timeout(match)
    state = match.game_state

    turn_info = state['turns'][state['current_turn']]
    if turn_info['player_role'] != player_num:
        return jsonify({'error': 'Not your turn'}), 403
    if state['phase'] != 'WAITING_BETS':
        return jsonify({'error': 'Not in betting phase'}), 400

    data = request.get_json()
    bets = data.get('bets', [])
    state, err = place_bets(state, bets)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/insurance', methods=['POST'])
@login_required
def api_insurance(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = _get_player_num(user, match)
    _check_and_handle_timeout(match)
    state = match.game_state

    turn_info = state['turns'][state['current_turn']]
    if turn_info['player_role'] != player_num:
        return jsonify({'error': 'Not your turn'}), 403
    if state['phase'] != 'INSURANCE':
        return jsonify({'error': 'Not in insurance phase'}), 400

    data = request.get_json()
    take = data.get('take', False)
    state, err = handle_insurance(state, take)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/action', methods=['POST'])
@login_required
def api_action(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = _get_player_num(user, match)
    _check_and_handle_timeout(match)
    state = match.game_state

    turn_info = state['turns'][state['current_turn']]
    if turn_info['player_role'] != player_num:
        return jsonify({'error': 'Not your turn'}), 403
    if state['phase'] != 'PLAYER_TURN':
        return jsonify({'error': 'Not in player turn phase'}), 400

    data = request.get_json()
    action = data.get('action')
    if action not in ('hit', 'stand', 'double', 'split'):
        return jsonify({'error': 'Invalid action'}), 400

    state, err = player_action(state, action)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/dealer_action', methods=['POST'])
@login_required
def api_dealer_action(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = _get_player_num(user, match)
    _check_and_handle_timeout(match)
    state = match.game_state

    turn_info = state['turns'][state['current_turn']]
    if turn_info['dealer_role'] != player_num:
        return jsonify({'error': 'Not your turn as dealer'}), 403
    if state['phase'] != 'DEALER_TURN':
        return jsonify({'error': 'Not in dealer turn phase'}), 400

    data = request.get_json()
    action = data.get('action')
    if action not in ('hit', 'stand'):
        return jsonify({'error': 'Invalid dealer action'}), 400

    state, err = dealer_action(state, action)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/next_round', methods=['POST'])
@login_required
def api_next_round(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = _get_player_num(user, match)
    _check_and_handle_timeout(match)
    state = match.game_state

    if state['phase'] != 'ROUND_RESULT':
        return jsonify({'error': 'Not in round result phase'}), 400

    state, match_ended = next_round_or_end_turn(state)
    clear_decision_timer(match)

    if match_ended:
        _settle_match(match, state)
    else:
        _set_timer_for_phase(match, state)

    match.game_state = state
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


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


@game_bp.route('/forfeit_match/<int:match_id>', methods=['POST'])
@login_required
def forfeit_match(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        flash('Cannot forfeit this match.', 'error')
        return redirect(url_for('game.lobby'))
    if user.id not in (match.player1_id, match.player2_id):
        flash('Not your match.', 'error')
        return redirect(url_for('game.lobby'))
    if user.id == match.player1_id:
        winner_id = match.player2_id
        winner_num = 2
    else:
        winner_id = match.player1_id
        winner_num = 1
    winner = User.query.get(winner_id)
    if winner:
        winner.coins += match.stake * 2
    match.winner_id = winner_id
    match.status = 'finished'
    clear_decision_timer(match)
    state = match.game_state or {}
    state['match_over'] = True
    state['phase'] = 'MATCH_OVER'
    state['match_result'] = {
        'player1_total': state.get('results', {}).get('player1') or 0,
        'player2_total': state.get('results', {}).get('player2') or 0,
        'winner': winner_num,
        'forfeit': True,
    }
    match.game_state = state
    _save_match(match)
    flash('You forfeited the match. Your stake goes to your opponent.', 'error')
    return redirect(url_for('game.lobby'))
