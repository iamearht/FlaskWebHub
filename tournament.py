from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, User, Match, Tournament, TournamentEntry, TournamentMatch
from auth import login_required, get_current_user
from engine import init_game_state
from datetime import datetime
import secrets

tournament_bp = Blueprint('tournament', __name__)

REQUIRED_PLAYERS = 8


def get_or_create_waiting_tournament(stake):
    tournament = Tournament.query.filter_by(
        stake_amount=stake,
        status='waiting'
    ).first()
    if not tournament:
        tournament = Tournament(stake_amount=stake, status='waiting', prize_pool=0)
        db.session.add(tournament)
        db.session.flush()
    return tournament


def start_tournament(tournament):
    entries = TournamentEntry.query.filter_by(tournament_id=tournament.id).all()
    if len(entries) < REQUIRED_PLAYERS:
        return

    shuffled = list(entries)
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]

    for i, entry in enumerate(shuffled):
        entry.seed = i + 1

    tournament.status = 'active'
    tournament.started_at = datetime.utcnow()
    tournament.prize_pool = tournament.stake_amount * REQUIRED_PLAYERS

    for i in range(0, REQUIRED_PLAYERS, 2):
        bracket_pos = i // 2
        p1 = shuffled[i]
        p2 = shuffled[i + 1]

        game_match = Match(
            player1_id=p1.user_id,
            player2_id=p2.user_id,
            stake=0,
            status='active',
            is_spectatable=True,
            game_state=init_game_state(),
        )
        db.session.add(game_match)
        db.session.flush()

        tm = TournamentMatch(
            tournament_id=tournament.id,
            round='quarterfinal',
            bracket_position=bracket_pos,
            player1_id=p1.user_id,
            player2_id=p2.user_id,
            match_id=game_match.id,
            status='active',
        )
        db.session.add(tm)

    for i in range(4):
        tm = TournamentMatch(
            tournament_id=tournament.id,
            round='semifinal',
            bracket_position=i // 2,
            status='pending',
        )
        db.session.add(tm)

    tm_final = TournamentMatch(
        tournament_id=tournament.id,
        round='final',
        bracket_position=0,
        status='pending',
    )
    db.session.add(tm_final)

    tm_third = TournamentMatch(
        tournament_id=tournament.id,
        round='third_place',
        bracket_position=0,
        status='pending',
    )
    db.session.add(tm_third)

    db.session.commit()


def advance_tournament(tournament, completed_match_id, winner_id, loser_id):
    tm = TournamentMatch.query.filter_by(
        tournament_id=tournament.id,
        match_id=completed_match_id,
    ).first()
    if not tm or tm.winner_id:
        return

    tm.winner_id = winner_id
    tm.status = 'completed'

    entry = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        user_id=loser_id,
    ).first()
    if entry:
        entry.eliminated_at = datetime.utcnow()

    if tm.round == 'quarterfinal':
        sf_pos = tm.bracket_position // 2
        sf_match = TournamentMatch.query.filter_by(
            tournament_id=tournament.id,
            round='semifinal',
            bracket_position=sf_pos,
        ).first()
        if sf_match:
            if tm.bracket_position % 2 == 0:
                sf_match.player1_id = winner_id
            else:
                sf_match.player2_id = winner_id

            if sf_match.player1_id and sf_match.player2_id:
                _create_match_for_tournament(sf_match, tournament)

    elif tm.round == 'semifinal':
        final_match = TournamentMatch.query.filter_by(
            tournament_id=tournament.id,
            round='final',
            bracket_position=0,
        ).first()
        third_match = TournamentMatch.query.filter_by(
            tournament_id=tournament.id,
            round='third_place',
            bracket_position=0,
        ).first()

        if final_match:
            if tm.bracket_position == 0:
                final_match.player1_id = winner_id
            else:
                final_match.player2_id = winner_id

            if final_match.player1_id and final_match.player2_id:
                _create_match_for_tournament(final_match, tournament)

        if third_match:
            if tm.bracket_position == 0:
                third_match.player1_id = loser_id
            else:
                third_match.player2_id = loser_id

            if third_match.player1_id and third_match.player2_id:
                _create_match_for_tournament(third_match, tournament)

    elif tm.round in ('final', 'third_place'):
        _check_tournament_complete(tournament)

    db.session.commit()


def _create_match_for_tournament(tm, tournament):
    game_match = Match(
        player1_id=tm.player1_id,
        player2_id=tm.player2_id,
        stake=0,
        status='active',
        is_spectatable=True,
        game_state=init_game_state(),
    )
    db.session.add(game_match)
    db.session.flush()
    tm.match_id = game_match.id
    tm.status = 'active'


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
        third.status = 'cancelled'

    for place, user_id in placements.items():
        payout_rate = Tournament.PAYOUTS.get(place, 0)
        payout = int(tournament.prize_pool * payout_rate)
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


@tournament_bp.route('/tournaments')
@login_required
def tournaments_page():
    user = get_current_user()
    active_tournaments = Tournament.query.filter(
        Tournament.status.in_(['waiting', 'active'])
    ).order_by(Tournament.stake_amount).all()

    my_entries = TournamentEntry.query.filter_by(user_id=user.id).all()
    my_tournament_ids = {e.tournament_id for e in my_entries}

    tournament_data = []
    for stake in Tournament.STAKES:
        waiting = Tournament.query.filter_by(stake_amount=stake, status='waiting').first()
        entry_count = 0
        user_joined = False
        if waiting:
            entry_count = TournamentEntry.query.filter_by(tournament_id=waiting.id).count()
            user_joined = waiting.id in my_tournament_ids

        active_list = Tournament.query.filter_by(
            stake_amount=stake, status='active'
        ).order_by(Tournament.started_at.desc()).limit(3).all()

        tournament_data.append({
            'stake': stake,
            'waiting': waiting,
            'entry_count': entry_count,
            'user_joined': user_joined,
            'active': active_list,
        })

    completed = Tournament.query.filter_by(status='completed')\
        .order_by(Tournament.completed_at.desc()).limit(10).all()

    return render_template('tournaments.html', user=user,
                           tournament_data=tournament_data, completed=completed)


@tournament_bp.route('/tournament/join/<int:stake>', methods=['POST'])
@login_required
def join_tournament(stake):
    user = get_current_user()
    if stake not in Tournament.STAKES:
        flash('Invalid tournament stake.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    if stake > user.coins:
        flash('Not enough coins to join this tournament.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    tournament = get_or_create_waiting_tournament(stake)

    existing = TournamentEntry.query.filter_by(
        tournament_id=tournament.id,
        user_id=user.id,
    ).first()
    if existing:
        flash('Already registered for this tournament.', 'error')
        return redirect(url_for('tournament.tournaments_page'))

    user.coins -= stake
    entry = TournamentEntry(tournament_id=tournament.id, user_id=user.id)
    db.session.add(entry)
    db.session.commit()

    entry_count = TournamentEntry.query.filter_by(tournament_id=tournament.id).count()
    if entry_count >= REQUIRED_PLAYERS:
        start_tournament(tournament)

    flash(f'Joined ${stake} tournament! ({entry_count}/{REQUIRED_PLAYERS} players)', 'success')
    return redirect(url_for('tournament.tournaments_page'))


@tournament_bp.route('/tournament/<int:tournament_id>')
@login_required
def view_tournament(tournament_id):
    user = get_current_user()
    tournament = Tournament.query.get_or_404(tournament_id)
    matches = TournamentMatch.query.filter_by(tournament_id=tournament_id)\
        .order_by(TournamentMatch.round, TournamentMatch.bracket_position).all()
    entries = TournamentEntry.query.filter_by(tournament_id=tournament_id)\
        .order_by(TournamentEntry.seed).all()

    bracket = {'quarterfinal': [], 'semifinal': [], 'final': [], 'third_place': []}
    for m in matches:
        bracket.setdefault(m.round, []).append(m)

    return render_template('tournament_view.html', user=user, tournament=tournament,
                           bracket=bracket, entries=entries)
