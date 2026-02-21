from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from sqlalchemy.orm.attributes import flag_modified
from models import (
    db, User, Match, Tournament, TournamentMatch,
    RakeTransaction, get_lobby_rake_percent,
    JackpotPool, JackpotEntry, get_jackpot_rake_percent,
    GAME_MODES, GAME_MODE_LIST
)
from auth import login_required, get_current_user
from engine import (
    init_game_state, enter_turn, place_bets, handle_insurance,
    player_action, dealer_action, next_round_or_end_turn, get_client_state,
    check_timeout, apply_timeout, set_decision_timer, clear_decision_timer,
    do_card_draw, make_choice, assign_joker_values, assign_dealer_joker_values
)

game_bp = Blueprint('game', __name__)


def _json(payload, status=200):
    """JSON response with aggressive no-cache headers (important for polling)."""
    resp = make_response(jsonify(payload), status)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _save_match(match):
    """
    Persist match changes immediately and invalidate the session cache.

    Critical: we flag_modified() to force-flush the JSON field even if mutated
    in-place, then commit, then expire_all() so the next read in this request
    cannot accidentally reuse stale identity-map data.
    """
    flag_modified(match, 'game_state')
    db.session.add(match)
    db.session.commit()
    db.session.expire_all()


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
            pt = JackpotPool.pool_type_for_mode(match.game_mode)
            pool = JackpotPool.get_active_pool(pt)
            pool.pool_amount += jackpot_contribution
            db.session.add(pool)

            winner = result.get('winner')
            if winner in (1, 2):
                winner_id = match.player1_id if winner == 1 else match.player2_id
                if winner_id:
                    je = JackpotEntry(user_id=winner_id, match_id=match.id, amount=jackpot_contribution)
                    db.session.add(je)

    winner = result.get('winner')
    if winner == 1:
        match.winner_id = match.player1_id
    elif winner == 2:
        match.winner_id = match.player2_id
    else:
        match.winner_id = None

    # pay winner net winnings (if not tournament/0 stake handled earlier)
    if match.winner_id and winnings > 0:
        u = User.query.get(match.winner_id)
        if u:
            u.coins += winnings

    match.status = 'finished'


# =========================
# Lobby / Match navigation
# =========================

@game_bp.route('/lobby')
@login_required
def lobby():
    user = get_current_user()
    sort_order = request.args.get('sort', 'desc')

    # -------------------------------------------------
    # ACTIVE MATCHES (ONLY MATCHES THIS USER IS IN)
    # -------------------------------------------------
    my_active = (
        Match.query
        .filter(
            Match.status == 'active',
            Match.tournament_match_id.is_(None),
            db.or_(
                Match.player1_id == user.id,
                Match.player2_id == user.id
            )
        )
        .order_by(Match.created_at.desc())
        .all()
    )

    # -------------------------------------------------
    # WAITING MATCHES (PUBLIC LOBBY LIST ONLY)
    # -------------------------------------------------
    waiting_query = (
        Match.query
        .filter(
            Match.status == 'waiting',
            Match.tournament_match_id.is_(None)
        )
    )

    if sort_order == 'asc':
        waiting_query = waiting_query.order_by(Match.stake.asc())
    else:
        waiting_query = waiting_query.order_by(Match.stake.desc())

    waiting = waiting_query.all()

    # -------------------------------------------------
    # Stake limits
    # -------------------------------------------------
    min_stake = 10
    max_stake = user.coins if user else 0

    # -------------------------------------------------
    # Jackpot pools (safe fallback)
    # -------------------------------------------------
    try:
        jackpot_pools = {
            "standard": JackpotPool.get_active_pool("classic"),
            "joker": JackpotPool.get_active_pool("classic_joker"),
            "interactive": JackpotPool.get_active_pool("interactive"),
            "interactive_joker": JackpotPool.get_active_pool("interactive_joker"),
        }
    except Exception:
        jackpot_pools = {
            "standard": None,
            "joker": None,
            "interactive": None,
            "interactive_joker": None,
        }

    # -------------------------------------------------
    # VIP / Rakeback
    # -------------------------------------------------
    vip = None
    rakeback = None

    try:
        vp = user.get_vip_progress()
        rp = user.get_rakeback_progress()

        vip = {
            'tier': vp.tier,
            'progress_percent': vp.progress_percent,
            'total_wagered': vp.total_wagered,
            'next_tier': vp.next_tier,
        }

        rakeback = {
            'tier': rp.tier,
            'total_rake_paid': rp.total_rake_paid,
        }
    except Exception:
        # Do NOT break lobby if VIP system fails
        pass

    return render_template(
        'lobby.html',
        user=user,
        my_active=my_active,
        waiting=waiting,
        min_stake=min_stake,
        max_stake=max_stake,
        sort_order=sort_order,
        game_modes=GAME_MODES,
        jackpot_pools=jackpot_pools,
        vip=vip,
        rakeback=rakeback
    )

# =========================
# Watch / Spectating hub
# =========================

@game_bp.route('/watch')
@login_required
def watch():
    # Top active lobby matches by stake
    top_lobby = Match.query.filter(
        Match.status == 'active',
        Match.tournament_match_id.is_(None),
        Match.is_spectatable.is_(True)
    ).order_by(Match.stake.desc()).limit(12).all()

    # Top active tournament matches by tournament stake
    try:
        from tournament import get_round_display_name
    except Exception:
        def get_round_display_name(rn, total_rounds=None):
            return rn.replace('_', ' ').title()

    q = (
        TournamentMatch.query
        .filter(TournamentMatch.match_id.isnot(None))
        .join(Match, Match.id == TournamentMatch.match_id)
        .join(Tournament, Tournament.id == TournamentMatch.tournament_id)
        .filter(Match.status == 'active', Match.is_spectatable.is_(True))
        .order_by(Tournament.stake_amount.desc())
        .limit(12)
    )

    tournament_display = []
    for tm in q.all():
        m = Match.query.get(tm.match_id) if tm.match_id else None
        if not m:
            continue
        tournament_display.append({
            'tournament': tm.tournament,
            'match': m,
            'p1': tm.player1,
            'p2': tm.player2,
            'round_name': get_round_display_name(tm.round),
        })

    return render_template(
        'watch.html',
        top_lobby=top_lobby,
        tournament_display=tournament_display
    )


@game_bp.route('/create_match', methods=['POST'])
@login_required
def create_match():
    user = get_current_user()

    try:
        stake = int(request.form.get('stake', 0))
    except (ValueError, TypeError):
        flash('Invalid stake amount.', 'error')
        return redirect(url_for('game.lobby'))

    game_mode = request.form.get('game_mode')
    if not game_mode or game_mode not in GAME_MODE_LIST:
        game_mode = 'classic'

    if stake < 10:
        flash('Minimum stake is 10 coins.', 'error')
        return redirect(url_for('game.lobby'))

    if stake > user.coins:
        flash('Not enough coins.', 'error')
        return redirect(url_for('game.lobby'))

    user.coins -= stake

    match = Match(
        player1_id=user.id,
        stake=stake,
        status='waiting',
        game_mode=game_mode
    )

    db.session.add(match)
    db.session.commit()

    flash(f'Match created with {stake} coin stake.', 'success')
    return redirect(url_for('game.lobby'))


@game_bp.route('/cancel_match/<int:match_id>', methods=['POST'])
@login_required
def cancel_match(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    # Only allow cancel if match is still waiting
    if match.status != 'waiting':
        flash('Match cannot be cancelled.', 'error')
        return redirect(url_for('game.lobby'))

    # Only creator can cancel
    if match.player1_id != user.id:
        flash('You cannot cancel this match.', 'error')
        return redirect(url_for('game.lobby'))

    # Refund stake
    user.coins += match.stake

    # Delete match
    db.session.delete(match)
    db.session.commit()

    flash('Match cancelled and stake refunded.', 'success')
    return redirect(url_for('game.lobby'))


@game_bp.route('/join_match/<int:match_id>', methods=['POST'])
@login_required
def join_match(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'waiting':
        flash('Match is no longer available.', 'error')
        return redirect(url_for('game.lobby'))

    if match.tournament_match_id is not None:
        flash('Cannot join this match from the lobby.', 'error')
        return redirect(url_for('game.lobby'))

    if match.player1_id == user.id:
        flash('Cannot join your own match.', 'error')
        return redirect(url_for('game.lobby'))

    if match.stake > user.coins:
        flash('Not enough coins to match the stake.', 'error')
        return redirect(url_for('game.lobby'))

    # Deduct stake
    user.coins -= match.stake

    # Attach player2
    match.player2_id = user.id
    match.status = 'active'

    # Initialize game state but DO NOT start timers yet
    state = init_game_state(game_mode=match.game_mode)
    match.game_state = state

    # IMPORTANT: no timer start here
    # DO NOT call _set_timer_for_phase()

    _save_match(match)

    flash('Match joined. Go to Lobby and press Play to enter.', 'success')
    return redirect(url_for('game.lobby'))

@game_bp.route('/forfeit_match/<int:match_id>', methods=['POST'])
@login_required
def forfeit_match(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        flash('Match is not active.', 'error')
        return redirect(url_for('game.lobby'))

    if match.tournament_match_id is not None:
        flash('Forfeit is disabled for tournament matches.', 'error')
        return redirect(url_for('game.lobby'))

    if user.id not in (match.player1_id, match.player2_id):
        flash('You are not a player in this match.', 'error')
        return redirect(url_for('game.lobby'))

    # Determine winner (opponent)
    forfeiter_player_num = 1 if user.id == match.player1_id else 2
    winner_player_num = 2 if forfeiter_player_num == 1 else 1

    # ---------------------------
    # SAFE STATE HANDLING
    # ---------------------------

    state = match.game_state

    # Guarantee state is a dict
    if not isinstance(state, dict):
        state = {}

    # Preserve previous totals if they exist
    previous_result = state.get('match_result') or {}

    state['match_over'] = True
    state['phase'] = 'MATCH_OVER'
    state['match_result'] = {
        'winner': winner_player_num,
        'forfeit': True,
        'player1_total': previous_result.get('player1_total', 0),
        'player2_total': previous_result.get('player2_total', 0),
    }

    match.game_state = state

    _settle_match(match, state)
    _save_match(match)

    flash('You forfeited the match.', 'success')
    return redirect(url_for('game.lobby'))


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
        cs = get_client_state(match.game_state, 1, match, spectator=True)
        p1 = User.query.get(match.player1_id)
        p2 = User.query.get(match.player2_id)
        return render_template('spectate.html', match=match, user=user, cs=cs, p1=p1, p2=p2)

    player_num = _get_player_num(user, match)
    cs = get_client_state(match.game_state, player_num, match)
    p1 = User.query.get(match.player1_id)
    p2 = User.query.get(match.player2_id)

    if match.status == 'finished':
        return render_template('match_result.html', match=match, user=user, cs=cs, p1=p1, p2=p2)

    return render_template('game.html', match=match, user=user, cs=cs, player_num=player_num, p1=p1, p2=p2, game_modes=GAME_MODES)


# =========================
# Polling state API
# =========================

@game_bp.route('/api/match/<int:match_id>/state')
@login_required
def api_state(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    is_player = user.id in (match.player1_id, match.player2_id)
    is_spectator = not is_player

    if is_spectator and not match.is_spectatable:
        return _json({'error': 'Not available for spectating'}, 403)

    state = match.game_state
    if state and 'turns' not in state and state.get('phase') not in ('CARD_DRAW', 'CHOICE'):
        return _json({'error': 'Old match format', 'status': 'finished'}, 400)

    # Advance timeouts regardless of who is viewing (player OR spectator)
    if match.status == 'active':
        _check_and_handle_timeout(match)
        # After timeout handling we may have committed; reload what’s persisted
        match = Match.query.get(match.id)

    if is_spectator:
        cs = get_client_state(match.game_state, 1, match, spectator=True)
        cs['is_spectator'] = True
        cs['status'] = match.status
        return _json(cs)

    player_num = _get_player_num(user, match)
    cs = get_client_state(match.game_state, player_num, match)
    cs['user_coins'] = User.query.get(user.id).coins
    cs['stake'] = match.stake
    cs['status'] = match.status
    return _json(cs)


# =========================
# Game action API routes
# =========================

@game_bp.route('/api/match/<int:match_id>/bet', methods=['POST'])
@login_required
def api_bet(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)
    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state
    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    bets = data.get('bets', [])

    state, err = place_bets(state, bets)
    if err:
        return _json({'error': err}, 400)

    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/insurance', methods=['POST'])
@login_required
def api_insurance(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)
    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state
    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    decisions = data.get('decisions', [])

    state, err = handle_insurance(state, decisions)
    if err:
        return _json({'error': err}, 400)

    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/action', methods=['POST'])
@login_required
def api_action(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)
    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state
    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    action = data.get('action')

    if action not in ('hit', 'stand', 'double', 'split'):
        return _json({'error': 'Invalid action'}, 400)

    state, err = player_action(state, action)
    if err:
        return _json({'error': err}, 400)

    if state.get('match_over'):
        _settle_match(match, state)

    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/choice', methods=['POST'])
@login_required
def api_choice(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)
    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state
    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    raw = data.get('go_first_as_player', True)
    # Accept strict booleans, but also tolerate string/number payloads.
    if isinstance(raw, str):
        raw = raw.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    go_first = bool(raw)

    state, err = make_choice(state, go_first)
    if err:
        return _json({'error': err}, 400)

    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    # IMPORTANT: return what is actually persisted
    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/next', methods=['POST'])
@game_bp.route('/api/match/<int:match_id>/next_round', methods=['POST'])
@login_required
def api_next(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)
    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state
    player_num = _get_player_num(user, match)

    state, ended = next_round_or_end_turn(state)

    if ended:
        _settle_match(match, state)

    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/joker', methods=['POST'])
@login_required
def api_joker(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    # --- Basic validation ---
    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)

    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state or {}

    # --- Critical: ensure correct phase ---
    if state.get('phase') != 'JOKER_CHOICE':
        return _json({'error': 'Not in joker selection phase'}, 400)

    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    values = data.get('values')

    # --- Validate payload ---
    if not isinstance(values, list) or not values:
        return _json({'error': 'Invalid joker values'}, 400)

    # Optional: enforce valid card ranks instead of numbers
    VALID = {"A","2","3","4","5","6","7","8","9","10"}

    # If you're now using ranks instead of numbers:
    for v in values:
        if isinstance(v, str):
            if v not in VALID:
                return _json({'error': f'Invalid joker rank: {v}'}, 400)
        else:
            # fallback numeric safety
            if not isinstance(v, int) or v < 1 or v > 11:
                return _json({'error': 'Invalid joker numeric value'}, 400)

    # --- Apply logic ---
    state, err = assign_joker_values(state, values)
    if err:
        return _json({'error': err}, 400)

    match.game_state = state

    # If joker resolution ended the match
    if state.get('match_over'):
        _settle_match(match, state)

    _set_timer_for_phase(match, state)
    _save_match(match)

    # Always return persisted state
    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/dealer_action', methods=['POST'])
@login_required
def api_dealer_action(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)
    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state
    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    action = data.get('action')

    if action not in ('hit', 'stand'):
        return _json({'error': 'Invalid dealer action'}, 400)

    state, err = dealer_action(state, action)
    if err:
        return _json({'error': err}, 400)

    if state.get('match_over'):
        _settle_match(match, state)

    match.game_state = state
    _set_timer_for_phase(match, state)
    _save_match(match)

    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


@game_bp.route('/api/match/<int:match_id>/dealer_joker', methods=['POST'])
@login_required
def api_dealer_joker(match_id):
    user = get_current_user()
    match = Match.query.get_or_404(match_id)

    # --- Basic validation ---
    if match.status != 'active':
        return _json({'error': 'Match not active'}, 400)

    if user.id not in (match.player1_id, match.player2_id):
        return _json({'error': 'Not your match'}, 403)

    state = match.game_state or {}

    # --- Critical: ensure correct phase ---
    if state.get('phase') != 'DEALER_JOKER_CHOICE':
        return _json({'error': 'Not in dealer joker selection phase'}, 400)

    player_num = _get_player_num(user, match)

    data = request.get_json(silent=True) or {}
    values = data.get('values')

    # --- Validate payload ---
    if not isinstance(values, list) or not values:
        return _json({'error': 'Invalid dealer joker values'}, 400)

    VALID = {"A","2","3","4","5","6","7","8","9","10"}

    for v in values:
        if isinstance(v, str):
            if v not in VALID:
                return _json({'error': f'Invalid joker rank: {v}'}, 400)
        else:
            if not isinstance(v, int) or v < 1 or v > 11:
                return _json({'error': 'Invalid joker numeric value'}, 400)

    # --- Apply engine logic ---
    state, err = assign_dealer_joker_values(state, values)
    if err:
        return _json({'error': err}, 400)

    match.game_state = state

    # If joker resolution ended the match
    if state.get('match_over'):
        _settle_match(match, state)

    _set_timer_for_phase(match, state)
    _save_match(match)

    # Return persisted state
    fresh = Match.query.get(match.id)
    return _json(get_client_state(fresh.game_state, player_num, fresh))


# =========================
# Misc APIs
# =========================

@game_bp.route('/api/my_active_matches')
@login_required
def api_my_active_matches():
    user = get_current_user()

    matches = Match.query.filter(
        Match.status.in_(['waiting', 'active']),
        db.or_(
            Match.player1_id == user.id,
            Match.player2_id == user.id
        )
    ).order_by(Match.created_at.desc()).all()

    data = []
    for m in matches:
        data.append({
            "id": m.id,
            "stake": m.stake,
            "status": m.status,
            "player1": m.player1.username if m.player1 else None,
            "player2": m.player2.username if m.player2 else None,
            "game_mode": m.game_mode,
        })

    return _json(data)


@game_bp.route('/api/match/<int:match_id>/ready')
@login_required
def api_match_ready(match_id):
    match = Match.query.get_or_404(match_id)

    return _json({
        "ready": match.status == "active"
    })