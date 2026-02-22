from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
import secrets
import math

from extensions import db
from models import (
    User, Match, Tournament, TournamentEntry, TournamentMatch,
    RakeTransaction, get_tournament_rake_percent, get_tournament_payouts,
    GAME_MODES, GAME_MODE_LIST
)

from auth import login_required, get_current_user
from engine import init_game_state

tournament_bp = Blueprint('tournament', __name__)


# ============================================================
# HELPERS
# ============================================================

def get_round_name(round_num, total_rounds):
    if round_num == total_rounds:
        return 'final'
    elif round_num == total_rounds - 1:
        return 'semifinal'
    elif round_num == total_rounds - 2:
        return 'quarterfinal'
    return f'round_{round_num}'


# ============================================================
# TOURNAMENT CREATION
# ============================================================

def get_or_create_waiting_tournament(stake, max_players, game_mode='classic'):
    tournament = Tournament.query.filter(
        Tournament.stake_amount == stake,
        Tournament.max_players == max_players,
        Tournament.game_mode == game_mode,
        Tournament.status == 'waiting'
    ).first()

    if not tournament:
        tournament = Tournament(
            stake_amount=stake,
            max_players=max_players,
            game_mode=game_mode,
            status='waiting',
            prize_pool=0
        )
        db.session.add(tournament)
        db.session.flush()

    return tournament


# ============================================================
# START TOURNAMENT
# ============================================================

def start_tournament(tournament):
    entries = TournamentEntry.query.filter_by(tournament_id=tournament.id).all()
    required = tournament.max_players

    if len(entries) < required:
        return

    shuffled = list(entries)
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]

    for i, entry in enumerate(shuffled):
        entry.seed = i + 1

    rake_percent = float(get_tournament_rake_percent(tournament.stake_amount, required))
    total_entry = tournament.stake_amount * required
    rake = int(total_entry * rake_percent / 100)

    tournament.rake_amount = rake
    tournament.prize_pool = total_entry - rake
    tournament.status = 'active'
    tournament.started_at = datetime.utcnow()

    if rake > 0:
        db.session.add(RakeTransaction(
            source_type='tournament',
            source_id=tournament.id,
            amount=rake,
            stake_amount=tournament.stake_amount,
            rake_percent=rake_percent,
        ))

    total_rounds = int(math.log2(required))
    first_round = get_round_name(1, total_rounds)

    for i in range(0, required, 2):
        p1 = shuffled[i]
        p2 = shuffled[i + 1]

        tm = TournamentMatch(
            tournament_id=tournament.id,
            round=first_round,
            bracket_position=i // 2,
            player1_id=p1.user_id,
            player2_id=p2.user_id,
            status='active'
        )
        db.session.add(tm)
        db.session.flush()

        match = Match(
            player1_id=p1.user_id,
            player2_id=p2.user_id,
            stake=0,
            status='active',
            is_spectatable=True,
            game_mode=tournament.game_mode,
            tournament_match_id=tm.id,
        )
        db.session.add(match)
        db.session.flush()

        init_game_state(match)

        tm.match_id = match.id

    db.session.commit()


# ============================================================
# ROUTES
# ============================================================

@tournament_bp.route('/tournaments')
@login_required
def tournaments_page():
    user = get_current_user()

    game_mode = request.args.get('mode', 'classic')
    if game_mode not in GAME_MODE_LIST:
        game_mode = 'classic'

    my_entries = TournamentEntry.query.filter_by(user_id=user.id).all()
    my_tournament_ids = {e.tournament_id for e in my_entries}

    tournament_data = []

    for stake in Tournament.STAKES:
        stake_variants = []

        for size in Tournament.PLAYER_SIZES:

            waiting = Tournament.query.filter(
                Tournament.stake_amount == stake,
                Tournament.max_players == size,
                Tournament.game_mode == game_mode,
                Tournament.status == 'waiting'
            ).first()

            entry_count = 0
            user_joined = False
            waiting_id = None

            if waiting:
                entry_count = TournamentEntry.query.filter_by(
                    tournament_id=waiting.id
                ).count()
                user_joined = waiting.id in my_tournament_ids
                waiting_id = waiting.id

            active_list = Tournament.query.filter(
                Tournament.stake_amount == stake,
                Tournament.max_players == size,
                Tournament.game_mode == game_mode,
                Tournament.status == 'active'
            ).order_by(Tournament.started_at.desc()).limit(2).all()

            rake_pct = float(get_tournament_rake_percent(stake, size))
            payouts = get_tournament_payouts(size)

            total_entry = stake * size
            rake = int(total_entry * rake_pct / 100)
            pool = total_entry - rake

            stake_variants.append({
                'size': size,
                'entry_count': entry_count,
                'user_joined': user_joined,
                'waiting_id': waiting_id,
                'active': active_list,
                'rake_pct': rake_pct,
                'pool': pool,
                'payouts': payouts,
            })

        tournament_data.append({
            'stake': stake,
            'stake_display': stake // 100,
            'variants': stake_variants,
        })

    completed = Tournament.query.filter(
        Tournament.status == 'completed'
    ).order_by(Tournament.completed_at.desc()).limit(10).all()

    return render_template(
        'tournaments.html',
        user=user,
        tournament_data=tournament_data,
        completed=completed,
        game_mode=game_mode,
        game_modes=GAME_MODES
    )


@tournament_bp.route('/tournament/join/<int:stake>/<int:size>', methods=['POST'])
@login_required
def join_tournament(stake, size):
    user = get_current_user()

    game_mode = request.args.get('mode', 'classic')
    if game_mode not in GAME_MODE_LIST:
        game_mode = 'classic'

    if stake > user.coins:
        flash('Not enough coins.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    tournament = get_or_create_waiting_tournament(stake, size, game_mode)

    existing = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        user_id=user.id
    ).first()

    if existing:
        flash('Already registered.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    user.coins -= stake
    db.session.add(TournamentEntry(
        tournament_id=tournament.id,
        user_id=user.id
    ))
    db.session.commit()

    entry_count = TournamentEntry.query.filter_by(
        tournament_id=tournament.id
    ).count()

    if entry_count >= size:
        start_tournament(tournament)

    flash('Joined tournament.', 'success')
    return redirect(url_for('tournament.tournaments_page'))
