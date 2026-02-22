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
from engine import init_game_state  # SQL-backed version

tournament_bp = Blueprint('tournament', __name__)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def get_round_name(round_num, total_rounds):
    if round_num == total_rounds:
        return 'final'
    elif round_num == total_rounds - 1:
        return 'semifinal'
    elif round_num == total_rounds - 2:
        return 'quarterfinal'
    return f'round_{round_num}'


def get_round_display_name(round_name, total_rounds=None):
    display_names = {
        'final': 'Final',
        'third_place': '3rd Place',
        'semifinal': 'Semifinal',
        'quarterfinal': 'Quarterfinal',
    }
    if round_name in display_names:
        return display_names[round_name]
    if round_name.startswith('round_'):
        num = round_name.replace('round_', '')
        return f'Round {num}'
    return round_name.replace('_', ' ').title()


def get_or_create_waiting_tournament(stake, max_players, game_mode='classic'):
    # IMPORTANT: filter by *_code columns, not string properties
    game_mode_code = Tournament.GAME_MODE_CODE.get(game_mode, Tournament.GAME_MODE_CODE['classic'])
    waiting_code = Tournament.TOURNAMENT_STATUS['waiting']

    tournament = Tournament.query.filter(
        Tournament.stake_amount == stake,
        Tournament.max_players == max_players,
        Tournament.game_mode_code == game_mode_code,
        Tournament.status_code == waiting_code,
    ).first()

    if not tournament:
        tournament = Tournament(
            stake_amount=stake,
            max_players=max_players,
            game_mode=game_mode,   # property setter -> game_mode_code
            status='waiting',      # property setter -> status_code
            prize_pool=0
        )
        db.session.add(tournament)
        db.session.flush()

    return tournament


# ------------------------------------------------------------
# Core tournament progression
# ------------------------------------------------------------

def start_tournament(tournament):
    """
    Creates the bracket and creates the FIRST ROUND matches.
    IMPORTANT: No JSON state. Matches are initialized via init_game_state(match).
    """
    entries = TournamentEntry.query.filter_by(tournament_id=tournament.id).all()
    required = tournament.max_players
    if len(entries) < required:
        return

    # Shuffle entries
    shuffled = list(entries)
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]

    # Assign seeds
    for i, entry in enumerate(shuffled):
        entry.seed = i + 1

    # Rake + pool
    rake_percent = get_tournament_rake_percent(tournament.stake_amount, required)
    total_entry = tournament.stake_amount * required
    rake = int(total_entry * rake_percent / 100)
    tournament.rake_amount = rake
    tournament.prize_pool = total_entry - rake

    if rake > 0:
        rt = RakeTransaction(
            source_type='tournament',
            source_id=tournament.id,
            amount=rake,
            stake_amount=tournament.stake_amount,
            rake_percent=rake_percent,
        )
        db.session.add(rt)

    tournament.status = 'active'
    tournament.started_at = datetime.utcnow()

    total_rounds = int(math.log2(required))
    first_round = get_round_name(1, total_rounds)

    # Create first round matches immediately
    for i in range(0, required, 2):
        bracket_pos = i // 2
        p1 = shuffled[i]
        p2 = shuffled[i + 1]

        tm = TournamentMatch(
            tournament_id=tournament.id,
            round=first_round,
            bracket_position=bracket_pos,
            player1_id=p1.user_id,
            player2_id=p2.user_id,
            status='active',   # property setter -> status_code
        )
        db.session.add(tm)
        db.session.flush()

        game_match = _create_game_match(
            tournament=tournament,
            player1_id=p1.user_id,
            player2_id=p2.user_id,
            tournament_match_id=tm.id,
            is_heads_up=False
        )

        tm.match_id = game_match.id

    # Create future rounds as pending bracket slots
    for r in range(2, total_rounds + 1):
        round_name = get_round_name(r, total_rounds)
        matches_in_round = required // (2 ** r)
        for pos in range(matches_in_round):
            db.session.add(TournamentMatch(
                tournament_id=tournament.id,
                round=round_name,
                bracket_position=pos,
                status='pending',  # property setter -> status_code
            ))

    # Create third place slot
    db.session.add(TournamentMatch(
        tournament_id=tournament.id,
        round='third_place',
        bracket_position=0,
        status='pending',  # property setter -> status_code
    ))

    db.session.commit()


def advance_tournament(tournament, completed_match_id, winner_id, loser_id):
    """
    Called when a tournament match ends.
    Updates bracket slots and spawns next match when both players known.
    """
    tm = TournamentMatch.query.filter_by(
        tournament_id=tournament.id,
        match_id=completed_match_id,
    ).first()

    if not tm or tm.winner_id:
        return

    tm.winner_id = winner_id
    tm.status = 'completed'

    # Mark loser eliminated
    entry = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        user_id=loser_id,
    ).first()
    if entry:
        entry.eliminated_at = datetime.utcnow()

    total_rounds = int(math.log2(tournament.max_players))
    all_rounds = [get_round_name(r, total_rounds) for r in range(1, total_rounds + 1)]

    current_round_idx = None
    for idx, rn in enumerate(all_rounds):
        if tm.round == rn:
            current_round_idx = idx
            break

    # Normal progression forward
    if current_round_idx is not None and current_round_idx < len(all_rounds) - 1:
        next_round = all_rounds[current_round_idx + 1]
        next_pos = tm.bracket_position // 2

        next_match = TournamentMatch.query.filter_by(
            tournament_id=tournament.id,
            round=next_round,
            bracket_position=next_pos,
        ).first()

        if next_match:
            if tm.bracket_position % 2 == 0:
                next_match.player1_id = winner_id
            else:
                next_match.player2_id = winner_id

            # Create match if ready
            if next_match.player1_id and next_match.player2_id and not next_match.match_id:
                is_final = (next_round == 'final')
                _create_match_for_tournament(next_match, tournament, is_final=is_final)

        # If moving into final, build third place from semifinal losers once both semis completed
        if next_round == 'final':
            third_match = TournamentMatch.query.filter_by(
                tournament_id=tournament.id,
                round='third_place',
                bracket_position=0,
            ).first()

            if third_match:
                sf_matches = TournamentMatch.query.filter_by(
                    tournament_id=tournament.id,
                    round=tm.round,  # should be 'semifinal' when next_round=='final'
                ).all()

                completed_sf = [m for m in sf_matches if m.status == 'completed']
                losers = []
                for m in completed_sf:
                    loser = m.player1_id if m.winner_id == m.player2_id else m.player2_id
                    losers.append((m.bracket_position, loser))
                losers.sort(key=lambda x: x[0])

                for pos, lid in losers:
                    if pos == 0 and not third_match.player1_id:
                        third_match.player1_id = lid
                    elif pos == 1 and not third_match.player2_id:
                        third_match.player2_id = lid

                if third_match.player1_id and third_match.player2_id and not third_match.match_id:
                    _create_match_for_tournament(third_match, tournament, is_final=False)

    # Special casing for semifinal (kept from your original logic)
    elif tm.round == 'semifinal':
        final_match = TournamentMatch.query.filter_by(
            tournament_id=tournament.id,
            round='final',
            bracket_position=0,
        ).first()

        if final_match:
            if tm.bracket_position == 0:
                final_match.player1_id = winner_id
            else:
                final_match.player2_id = winner_id

            if final_match.player1_id and final_match.player2_id and not final_match.match_id:
                _create_match_for_tournament(final_match, tournament, is_final=True)

        third_match = TournamentMatch.query.filter_by(
            tournament_id=tournament.id,
            round='third_place',
            bracket_position=0,
        ).first()

        if third_match:
            if tm.bracket_position == 0:
                third_match.player1_id = loser_id
            else:
                third_match.player2_id = loser_id

            if third_match.player1_id and third_match.player2_id and not third_match.match_id:
                _create_match_for_tournament(third_match, tournament, is_final=False)

    # When final/third ends: complete tournament
    elif tm.round in ('final', 'third_place'):
        _check_tournament_complete(tournament)

    db.session.commit()


# ------------------------------------------------------------
# Match creation helpers
# ------------------------------------------------------------

def _create_game_match(tournament, player1_id, player2_id, tournament_match_id, is_heads_up):
    """
    Creates Match row and initializes SQL engine state (MatchState/Turns/etc).
    """
    game_match = Match(
        player1_id=player1_id,
        player2_id=player2_id,
        stake=0,
        status='active',               # property setter -> status_code
        is_spectatable=True,
        game_mode=tournament.game_mode,  # property setter -> game_mode_code
        tournament_match_id=tournament_match_id,
    )
    db.session.add(game_match)
    db.session.flush()

    # Initialize SQL state machine
    # Prefer init_game_state(match, is_heads_up=...) if your engine supports it
    try:
        init_game_state(game_match, is_heads_up=is_heads_up)
    except TypeError:
        # Engine signature is init_game_state(match)
        init_game_state(game_match)

    return game_match


def _create_match_for_tournament(tm, tournament, is_final=False):
    """
    Creates the actual Match row for a pending TournamentMatch when both players are known.
    """
    game_match = _create_game_match(
        tournament=tournament,
        player1_id=tm.player1_id,
        player2_id=tm.player2_id,
        tournament_match_id=tm.id,
        is_heads_up=is_final
    )
    tm.match_id = game_match.id
    tm.status = 'active'


# ------------------------------------------------------------
# Tournament completion + payouts
# ------------------------------------------------------------

def _check_tournament_complete(tournament):
    final = TournamentMatch.query.filter_by(
        tournament_id=tournament.id,
        round='final',
    ).first()

    third = TournamentMatch.query.filter_by(
        tournament_id=tournament.id,
        round='third_place',
    ).first()

    if not final or not final.winner_id:
        return

    tournament.status = 'completed'
    tournament.completed_at = datetime.utcnow()

    final_loser = final.player1_id if final.winner_id == final.player2_id else final.player2_id
    placements = {1: final.winner_id, 2: final_loser}

    if third and third.winner_id:
        third_loser = third.player1_id if third.winner_id == third.player2_id else third.player2_id
        placements[3] = third.winner_id
        placements[4] = third_loser
    elif third and not third.player1_id and not third.player2_id:
        third.status = 'cancelled'  # Note: your TournamentMatch.STATUS does not include 'cancelled'

    payouts = get_tournament_payouts(tournament.max_players)

    for place, user_id in placements.items():
        payout_pct = payouts.get(place, 0)
        payout = int(tournament.prize_pool * payout_pct / 100)
        if payout > 0:
            user = User.query.get(user_id)
            if user:
                user.coins += payout

        entry = TournamentEntry.query.filter_by(
            tournament_id=tournament.id,
            user_id=user_id,
        ).first()
        if entry:
            entry.placement = place

    db.session.commit()


# ------------------------------------------------------------
# Routes (unchanged except they now rely on SQL matches)
# ------------------------------------------------------------

@tournament_bp.route('/tournaments')
@login_required
def tournaments_page():
    user = get_current_user()

    game_mode = request.args.get('mode', 'classic')
    if game_mode not in GAME_MODE_LIST:
        game_mode = 'classic'

    game_mode_code = Tournament.GAME_MODE_CODE.get(game_mode, Tournament.GAME_MODE_CODE['classic'])
    waiting_code = Tournament.TOURNAMENT_STATUS['waiting']
    active_code = Tournament.TOURNAMENT_STATUS['active']
    completed_code = Tournament.TOURNAMENT_STATUS['completed']

    my_entries = TournamentEntry.query.filter_by(user_id=user.id).all()
    my_tournament_ids = {e.tournament_id for e in my_entries}

    tournament_data = []
    for stake in Tournament.STAKES:
        stake_variants = []
        for size in Tournament.PLAYER_SIZES:
            waiting = Tournament.query.filter(
                Tournament.stake_amount == stake,
                Tournament.max_players == size,
                Tournament.game_mode_code == game_mode_code,
                Tournament.status_code == waiting_code
            ).first()

            entry_count = 0
            user_joined = False
            waiting_id = None
            if waiting:
                entry_count = TournamentEntry.query.filter_by(tournament_id=waiting.id).count()
                user_joined = waiting.id in my_tournament_ids
                waiting_id = waiting.id

            active_list = Tournament.query.filter(
                Tournament.stake_amount == stake,
                Tournament.max_players == size,
                Tournament.game_mode_code == game_mode_code,
                Tournament.status_code == active_code
            ).order_by(Tournament.started_at.desc()).limit(2).all()

            rake_pct = get_tournament_rake_percent(stake, size)
            try:
                rake_pct = float(rake_pct)
            except (TypeError, ValueError):
                rake_pct = 5.0  # safe fallback

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
        Tournament.status_code == completed_code
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

    if stake not in Tournament.STAKES:
        flash('Invalid tournament stake.', 'error')
        return redirect(url_for('tournament.tournaments_page', mode=game_mode))

    if size not in Tournament.PLAYER_SIZES:
        flash('Invalid tournament size.', 'error')
        return redirect(url_for('tournament.tournaments_page', mode=game_mode))

    if stake > user.coins:
        flash('Not enough coins to join this tournament.', 'error')
        return redirect(url_for('tournament.tournaments_page', mode=game_mode))

    tournament = get_or_create_waiting_tournament(stake, size, game_mode)

    existing = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        user_id=user.id,
    ).first()
    if existing:
        flash('Already registered for this tournament.', 'error')
        return redirect(url_for('tournament.tournaments_page', mode=game_mode))

    user.coins -= stake
    entry = TournamentEntry(tournament_id=tournament.id, user_id=user.id)
    db.session.add(entry)
    db.session.commit()

    entry_count = TournamentEntry.query.filter_by(tournament_id=tournament.id).count()
    if entry_count >= size:
        start_tournament(tournament)

    flash(f'Joined {stake} coin tournament! ({entry_count}/{size} players)', 'success')
    return redirect(url_for('tournament.tournaments_page', mode=game_mode))


@tournament_bp.route('/tournament/unregister/<int:tournament_id>', methods=['POST'])
@login_required
def unregister_tournament(tournament_id):
    user = get_current_user()
    tournament = Tournament.query.get_or_404(tournament_id)

    if tournament.status != 'waiting':
        flash('Cannot unregister from a tournament that has already started.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    entry = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        user_id=user.id,
    ).first()
    if not entry:
        flash('You are not registered for this tournament.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    user.coins += tournament.stake_amount
    db.session.delete(entry)
    db.session.commit()

    flash(f'Unregistered from tournament. {tournament.stake_amount} coins refunded.', 'success')
    return redirect(url_for('tournament.tournaments_page'))


@tournament_bp.route('/tournament/<int:tournament_id>')
@login_required
def view_tournament(tournament_id):
    user = get_current_user()
    tournament = Tournament.query.get_or_404(tournament_id)

    matches = TournamentMatch.query.filter_by(tournament_id=tournament_id) \
        .order_by(TournamentMatch.round, TournamentMatch.bracket_position).all()

    entries = TournamentEntry.query.filter_by(tournament_id=tournament_id) \
        .order_by(TournamentEntry.seed).all()

    total_rounds = int(math.log2(tournament.max_players))
    round_order = [get_round_name(r, total_rounds) for r in range(1, total_rounds + 1)]
    round_order.append('third_place')

    bracket = {rn: [] for rn in round_order}
    for m in matches:
        bracket.setdefault(m.round, []).append(m)

    round_display = {rn: get_round_display_name(rn, total_rounds) for rn in round_order}
    payouts = get_tournament_payouts(tournament.max_players)

    return render_template(
        'tournament_view.html',
        user=user,
        tournament=tournament,
        bracket=bracket,
        entries=entries,
        round_order=round_order,
        round_display=round_display,
        payouts=payouts
    )
