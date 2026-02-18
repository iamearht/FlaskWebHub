from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy.orm.attributes import flag_modified
from models import (db, User, Match, Tournament, TournamentMatch, VIPProgress,
                     RakeTransaction, RakebackProgress, get_lobby_rake_percent,
                     JackpotPool, JackpotEntry, get_jackpot_rake_percent,
                     GAME_MODES, GAME_MODE_LIST)
from auth import login_required, get_current_user
from engine import (
    init_game_state, enter_turn, place_bets, handle_insurance,
    player_action, dealer_action, next_round_or_end_turn, get_client_state,
    check_timeout, apply_timeout, set_decision_timer, clear_decision_timer,
    do_card_draw, make_choice, assign_joker_values, assign_dealer_joker_values
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
    game_mode = state.get('game_mode', 'classic')
    if phase == 'CHOICE':
        set_decision_timer(match, 'CHOICE')
    elif phase == 'WAITING_BETS':
        set_decision_timer(match, 'BET')
    elif phase == 'INSURANCE':
        set_decision_timer(match, 'INSURANCE')
    elif phase == 'JOKER_CHOICE':
        set_decision_timer(match, 'JOKER')
    elif phase == 'PLAYER_TURN':
        set_decision_timer(match, 'ACTION')
    elif phase == 'DEALER_JOKER_CHOICE':
        set_decision_timer(match, 'DEALER_JOKER')
    elif phase == 'DEALER_TURN':
        if game_mode in ('classic', 'classic_joker'):
            clear_decision_timer(match)
        else:
            set_decision_timer(match, 'DEALER')
    elif phase == 'ROUND_RESULT':
        set_decision_timer(match, 'NEXT')
    elif phase in ('TURN_START', 'MATCH_OVER', 'CARD_DRAW'):
        clear_decision_timer(match)


def _settle_match(match, state):
    result = state['match_result']
    total_pot = match.stake * 2
    is_tournament = match.tournament_match_id is not None

    if is_tournament or match.stake == 0:
        rake = 0
    else:
        rake_pct = get_lobby_rake_percent(match.stake)
        rake = int(total_pot * rake_pct / 100)

    match.rake_amount = rake
    winnings = total_pot - rake

    if rake > 0:
        rt = RakeTransaction(
            source_type='match',
            source_id=match.id,
            amount=rake,
            stake_amount=match.stake,
            rake_percent=get_lobby_rake_percent(match.stake),
        )
        db.session.add(rt)

        jackpot_pct = get_jackpot_rake_percent()
        jackpot_contribution = int(rake * jackpot_pct / 100)
        if jackpot_contribution > 0:
            pool = JackpotPool.get_active_pool()
            pool.pool_amount += jackpot_contribution

        for pid in [match.player1_id, match.player2_id]:
            if pid:
                user = User.query.get(pid)
                if user:
                    rp = user.get_rakeback_progress()
                    rb_pct = rp.rakeback_percent
                    rp.add_rake(rake / 2)
                    if rb_pct > 0:
                        rb_credit = int((rake / 2) * rb_pct / 100)
                        if rb_credit > 0:
                            user.coins += rb_credit

    if not is_tournament and match.stake > 0:
        _record_jackpot_scores(match, state)

    if result['winner'] == 1:
        p1 = User.query.get(match.player1_id)
        p1.coins += winnings
        match.winner_id = match.player1_id
    elif result['winner'] == 2:
        p2 = User.query.get(match.player2_id)
        p2.coins += winnings
        match.winner_id = match.player2_id
    else:
        p1 = User.query.get(match.player1_id)
        p2 = User.query.get(match.player2_id)
        share = winnings // 2
        p1.coins += share
        p2.coins += share
        match.winner_id = None
    match.status = 'finished'

    if match.stake > 0:
        _track_vip_and_affiliate(match)

    _check_tournament_advancement(match)


def _record_jackpot_scores(match, state):
    pool = JackpotPool.get_active_pool()

    results = state.get('results', {})
    for player_num, pid in [(1, match.player1_id), (2, match.player2_id)]:
        if not pid:
            continue
        turn1_key = f'player{player_num}_turn1'
        turn2_key = f'player{player_num}_turn2'
        t1 = results.get(turn1_key) or 0
        t2 = results.get(turn2_key) or 0
        total_chips = t1 + t2
        if total_chips <= 0:
            continue
        score = total_chips * match.stake
        entry = JackpotEntry(
            jackpot_id=pool.id,
            user_id=pid,
            match_id=match.id,
            score=score,
            finishing_chips=total_chips,
            match_stake=match.stake,
        )
        db.session.add(entry)


def _track_vip_and_affiliate(match):
    import logging
    logger = logging.getLogger(__name__)
    for pid in [match.player1_id, match.player2_id]:
        if not pid:
            continue
        user = User.query.get(pid)
        if user:
            vp = user.get_vip_progress()
            vp.add_wager(match.stake)

    from affiliate import process_affiliate_commission
    try:
        process_affiliate_commission(match)
    except Exception as e:
        logger.error(f"Affiliate commission error for match {match.id}: {e}")


def _check_tournament_advancement(match):
    import logging
    logger = logging.getLogger(__name__)
    tm = TournamentMatch.query.filter_by(match_id=match.id).first()
    if not tm:
        return

    tournament = Tournament.query.get(tm.tournament_id)
    if not tournament:
        return

    if match.winner_id:
        loser_id = match.player2_id if match.winner_id == match.player1_id else match.player1_id
        from tournament import advance_tournament
        try:
            advance_tournament(tournament, match.id, match.winner_id, loser_id)
        except Exception as e:
            logger.error(f"Tournament advancement error for match {match.id}, tournament {tournament.id}: {e}")
            raise


@game_bp.route('/lobby')
@login_required
def lobby():
    user = get_current_user()

    game_mode = request.args.get('mode', 'classic')
    if game_mode not in GAME_MODE_LIST:
        game_mode = 'classic'
    min_stake = request.args.get('min_stake', '', type=str)
    max_stake = request.args.get('max_stake', '', type=str)
    sort_order = request.args.get('sort', 'newest')

    waiting_q = Match.query.filter_by(status='waiting', game_mode=game_mode).filter(
        Match.player1_id != user.id,
        Match.tournament_match_id.is_(None),
    )

    if min_stake and min_stake.isdigit():
        waiting_q = waiting_q.filter(Match.stake >= int(min_stake))
    if max_stake and max_stake.isdigit():
        waiting_q = waiting_q.filter(Match.stake <= int(max_stake))

    if sort_order == 'low_high':
        waiting_q = waiting_q.order_by(Match.stake.asc())
    elif sort_order == 'high_low':
        waiting_q = waiting_q.order_by(Match.stake.desc())
    else:
        waiting_q = waiting_q.order_by(Match.created_at.desc())

    waiting = waiting_q.all()

    my_matches = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status.in_(['waiting', 'active'])
    ).all()
    history = Match.query.filter(
        ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        Match.status == 'finished'
    ).order_by(Match.created_at.desc()).limit(10).all()

    live_games = Match.query.filter_by(
        status='active', is_spectatable=True
    ).filter(
        Match.player1_id != user.id,
        Match.player2_id != user.id,
    ).order_by(Match.created_at.desc()).limit(10).all()

    vip = user.get_vip_progress()
    rakeback = user.get_rakeback_progress()

    jackpot_pool = JackpotPool.get_active_pool()
    db.session.commit()

    return render_template('lobby.html', user=user, waiting=waiting, my_matches=my_matches,
                           history=history, live_games=live_games, vip=vip, rakeback=rakeback,
                           min_stake=min_stake, max_stake=max_stake, sort_order=sort_order,
                           game_mode=game_mode, game_modes=GAME_MODES,
                           jackpot_pool=jackpot_pool)


@game_bp.route('/create_match', methods=['POST'])
@login_required
def create_match():
    user = get_current_user()
    try:
        stake = int(request.form.get('stake', 0))
    except (ValueError, TypeError):
        flash('Invalid stake amount.', 'error')
        return redirect(url_for('game.lobby'))
    game_mode = request.form.get('game_mode', 'classic')
    if game_mode not in GAME_MODE_LIST:
        game_mode = 'classic'
    if stake < 10:
        flash('Minimum stake is 10 coins.', 'error')
        return redirect(url_for('game.lobby', mode=game_mode))
    if stake > user.coins:
        flash('Not enough coins.', 'error')
        return redirect(url_for('game.lobby', mode=game_mode))

    user.coins -= stake
    match = Match(player1_id=user.id, stake=stake, status='waiting', game_mode=game_mode)
    db.session.add(match)
    db.session.commit()
    flash(f'Match created with {stake} coin stake.', 'success')
    return redirect(url_for('game.lobby', mode=game_mode))


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
    state = init_game_state(game_mode=match.game_mode)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)
    return redirect(url_for('game.play', match_id=match.id))


@game_bp.route('/match/<int:match_id>')
@login_required
def play(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    is_player = user.id in (match.player1_id, match.player2_id)
    is_spectator = not is_player

    if is_spectator and not match.is_spectatable:
        flash('This match is not available for spectating.', 'error')
        return redirect(url_for('game.lobby'))

    if match.status == 'waiting':
        if is_player:
            return render_template('waiting.html', match=match, user=user)
        flash('Match has not started yet.', 'error')
        return redirect(url_for('game.lobby'))

    state = match.game_state
    if state and 'turns' not in state and state.get('phase') not in ('CARD_DRAW', 'CHOICE'):
        if is_player:
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

    if match.status == 'active' and is_player:
        _check_and_handle_timeout(match)

    if is_spectator:
        state = match.game_state
        cs = get_client_state(state, 1, match, spectator=True)
        p1 = User.query.get(match.player1_id)
        p2 = User.query.get(match.player2_id)
        return render_template('spectate.html', match=match, user=user, cs=cs, p1=p1, p2=p2)

    player_num = _get_player_num(user, match)
    state = match.game_state
    p1 = User.query.get(match.player1_id)
    p2 = User.query.get(match.player2_id)

    if match.status == 'finished':
        cs = get_client_state(state, player_num, match)
        return render_template('match_result.html', match=match, user=user, cs=cs, p1=p1, p2=p2)

    cs = get_client_state(state, player_num, match)
    return render_template('game.html', match=match, user=user, cs=cs, player_num=player_num, p1=p1, p2=p2, game_modes=GAME_MODES)


@game_bp.route('/api/my_active_matches')
@login_required
def api_my_active_matches():
    user = get_current_user()
    active_matches = Match.query.filter(
        Match.status == 'active',
        db.or_(Match.player1_id == user.id, Match.player2_id == user.id),
    ).order_by(Match.created_at.desc()).all()

    results = []
    for m in active_matches:
        opponent_id = m.player2_id if m.player1_id == user.id else m.player1_id
        opponent = User.query.get(opponent_id) if opponent_id else None
        results.append({
            'match_id': m.id,
            'stake': m.stake,
            'opponent': opponent.username if opponent else 'Unknown',
            'game_mode': m.game_mode,
            'is_tournament': m.tournament_match_id is not None,
        })
    return jsonify(results)


@game_bp.route('/api/match/<int:match_id>/state')
@login_required
def api_state(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    is_player = user.id in (match.player1_id, match.player2_id)
    is_spectator = not is_player

    if is_spectator and not match.is_spectatable:
        return jsonify({'error': 'Not available for spectating'}), 403

    state = match.game_state
    if state and 'turns' not in state and state.get('phase') not in ('CARD_DRAW', 'CHOICE'):
        return jsonify({'error': 'Old match format', 'status': 'finished'}), 400

    if match.status == 'active' and is_player:
        _check_and_handle_timeout(match)

    if is_spectator:
        cs = get_client_state(match.game_state, 1, match, spectator=True)
        cs['is_spectator'] = True
        cs['status'] = match.status
        return jsonify(cs)

    player_num = _get_player_num(user, match)
    cs = get_client_state(match.game_state, player_num, match)
    cs['user_coins'] = User.query.get(user.id).coins
    cs['stake'] = match.stake
    cs['status'] = match.status
    return jsonify(cs)


@game_bp.route('/api/match/<int:match_id>/draw', methods=['POST'])
@login_required
def api_draw(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400
    if user.id not in (match.player1_id, match.player2_id):
        return jsonify({'error': 'Not your match'}), 403

    _check_and_handle_timeout(match)
    state = match.game_state

    if state['phase'] != 'CARD_DRAW':
        return jsonify({'error': 'Not in card draw phase'}), 400

    state, err = do_card_draw(state)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    player_num = _get_player_num(user, match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/choice', methods=['POST'])
@login_required
def api_choice(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)
    if match.status != 'active':
        return jsonify({'error': 'Match not active'}), 400

    player_num = _get_player_num(user, match)
    _check_and_handle_timeout(match)
    state = match.game_state

    if state['phase'] != 'CHOICE':
        return jsonify({'error': 'Not in choice phase'}), 400
    if state['chooser'] != player_num:
        return jsonify({'error': 'Not your choice to make'}), 403

    data = request.get_json()
    go_first = data.get('go_first_as_player', True)

    state, err = make_choice(state, go_first)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


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
    decisions = data.get('decisions', [])
    if not decisions:
        take_all = data.get('take', False)
        num_hands = sum(len(box['hands']) for box in state['turn_state']['round']['boxes'])
        decisions = [take_all] * num_hands
    state, err = handle_insurance(state, decisions)
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


@game_bp.route('/api/match/<int:match_id>/joker_choice', methods=['POST'])
@login_required
def api_joker_choice(match_id):
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
    if state['phase'] != 'JOKER_CHOICE':
        return jsonify({'error': 'Not in joker choice phase'}), 400

    data = request.get_json()
    values = data.get('values', [])
    state, err = assign_joker_values(state, values)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    if state.get('match_over'):
        _settle_match(match, state)
    _save_match(match)
    return jsonify(get_client_state(state, player_num, match))


@game_bp.route('/api/match/<int:match_id>/dealer_joker_choice', methods=['POST'])
@login_required
def api_dealer_joker_choice(match_id):
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
    if state['phase'] != 'DEALER_JOKER_CHOICE':
        return jsonify({'error': 'Not in dealer joker choice phase'}), 400

    data = request.get_json()
    values = data.get('values', [])
    state, err = assign_dealer_joker_values(state, values)
    if err:
        return jsonify({'error': err}), 400

    clear_decision_timer(match)
    match.game_state = state
    _set_timer_for_phase(match, state)
    if state.get('match_over'):
        _settle_match(match, state)
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
        'player1_total': 0,
        'player2_total': 0,
        'winner': winner_num,
        'forfeit': True,
    }
    match.game_state = state

    if match.stake > 0:
        _track_vip_and_affiliate(match)
    _check_tournament_advancement(match)

    _save_match(match)
    flash('You forfeited the match. Your stake goes to your opponent.', 'error')
    return redirect(url_for('game.lobby'))
