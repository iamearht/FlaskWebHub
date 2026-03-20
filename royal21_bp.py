"""
Royal 21 Flask blueprint.
HTTP routes for the table page + Flask-SocketIO event handlers for real-time game.
"""
import logging
from flask import Blueprint, render_template, abort, request
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room

from extensions import db
from models import Royal21Table, Royal21Seat, User
from royal21_manager import get_table, get_or_create_table, all_table_ids, TableState
from royal21.engine.betting import BettingCalculator
from royal21.rules.hand_rankings import evaluate_hand, find_winners
from royal21.engine.pot_manager import PotManager

log = logging.getLogger(__name__)

royal21_bp = Blueprint('royal21', __name__, url_prefix='/royal21')

# Injected by app.py after SocketIO is initialised
socketio = None


def init_socketio(sio):
    """Called from app.py to give the blueprint a reference to SocketIO."""
    global socketio
    socketio = sio
    _register_socketio_events(sio)


# ---------------------------------------------------------------------------
# HTTP Routes
# ---------------------------------------------------------------------------

@royal21_bp.route('/table/<int:table_id>')
@login_required
def table_view(table_id):
    table = Royal21Table.query.get_or_404(table_id)
    if not table.is_open:
        abort(403)
    my_seat_rec = Royal21Seat.query.filter_by(
        table_id=table_id, user_id=current_user.id
    ).first()
    return render_template(
        'royal21_table.html',
        table=table,
        user=current_user,
        my_seat_rec=my_seat_rec,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOM = lambda tid: f'royal21_{tid}'


def _collect_bets(engine):
    """Move all pending current_bets into main_pot and reset current_bet to 0."""
    state = engine.state
    for player in state.players.values():
        state.pot.main_pot += player.current_bet
        player.current_bet = 0
    state.current_high_bet = 0


def _build_state(ts: TableState, viewing_seat=None) -> dict:
    """Build a JSON-serialisable game state dict for one viewer."""
    state = {
        'table_id': ts.table_id,
        'ante': ts.ante,
        'min_buyin': ts.min_buyin,
        'max_buyin': ts.max_buyin,
        'phase': 'WAITING',
        'hand_number': 0,
        'pot': 0,
        'current_actor': None,
        'current_high_bet': 0,
        'button_seat': None,
        'players': [],
        'ready_seats': list(ts.ready_seats),
        'available_seats': ts.get_available_seats(),
        'legal_actions': [],
        'showdown_result': None,
    }

    # Seated players (from seating manager)
    for seat_num in range(7):
        seat_obj = ts.seating.seats[seat_num]
        if seat_obj.player_id is None:
            continue
        player_info = {
            'seat': seat_num,
            'name': seat_obj.player_name,
            'player_id': str(seat_obj.player_id),
            'stack': seat_obj.stack,
            'is_ready': seat_num in ts.ready_seats,
            'hole_cards': [],
            'current_bet': 0,
            'is_folded': False,
            'is_all_in': False,
            'is_bust': False,
            'exposed_card': None,
        }
        state['players'].append(player_info)

    if not ts.engine:
        return state

    gs = ts.engine.state
    state['phase'] = gs.phase
    state['hand_number'] = gs.hand_number
    state['pot'] = gs.pot.main_pot + sum(p.current_bet for p in gs.players.values())
    state['current_actor'] = gs.current_actor
    state['current_high_bet'] = gs.current_high_bet
    state['button_seat'] = gs.button_seat

    for player_info in state['players']:
        sn = player_info['seat']
        if sn not in gs.players:
            continue
        gp = gs.players[sn]
        player_info['stack'] = gp.stack
        player_info['current_bet'] = gp.current_bet
        player_info['is_folded'] = gp.is_folded
        player_info['is_all_in'] = gp.is_all_in
        player_info['is_bust'] = gp.is_bust

        # Hole cards — owner sees all; others see only revealed card
        cards_out = []
        for i, c in enumerate(gp.hole_cards):
            if viewing_seat == sn or i == gp.exposed_card_index:
                cards_out.append({'rank': c.rank, 'suit': c.suit, 'display': c.display})
            else:
                cards_out.append({'rank': '?', 'suit': '?', 'display': '??'})
        player_info['hole_cards'] = cards_out

        # Exposed card info
        if gp.exposed_card_index is not None and gp.exposed_card_index < len(gp.hole_cards):
            c = gp.hole_cards[gp.exposed_card_index]
            player_info['exposed_card'] = {
                'rank': c.rank, 'suit': c.suit,
                'display': c.display, 'index': gp.exposed_card_index,
            }

    # Legal actions for viewing player if it's their turn
    if gs.current_actor is not None and viewing_seat == gs.current_actor:
        state['legal_actions'] = ts.engine.get_legal_actions(gs.current_actor)

    return state


def _broadcast(ts: TableState, extra: dict = None):
    """
    Broadcast public state to the room, then emit private state (with hole
    cards) to each player individually via their SID.
    """
    room = ROOM(ts.table_id)

    # Public state (no private cards)
    pub = _build_state(ts, viewing_seat=None)
    if extra:
        pub.update(extra)
    socketio.emit('royal21_state', pub, room=room)

    # Private state per player (with their own hole cards + their legal actions)
    for pid, sid in list(ts.player_sids.items()):
        seat = ts.get_player_seat(pid)
        if seat is None:
            continue
        priv = _build_state(ts, viewing_seat=seat)
        if extra:
            priv.update(extra)
        socketio.emit('royal21_private', priv, room=sid)


def _refund_player_coins(user_id: int, amount: int):
    """Add `amount` coins back to the user's account and commit."""
    try:
        user = User.query.get(user_id)
        if user and amount > 0:
            user.coins = int(user.coins) + amount
            db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Failed to refund coins to user %s", user_id)


def _remove_player_from_table(ts: TableState, user_id: int, sid: str = None):
    """
    Remove a player from the in-memory table and refund their remaining stack.
    Also cleans up the Royal21Seat DB record.
    """
    seat = ts.get_player_seat(user_id)
    if seat is None:
        return

    # Determine refund amount: engine stack if mid-game, else seating stack
    if ts.engine and seat in ts.engine.state.players:
        refund = ts.engine.state.players[seat].stack
    else:
        refund = ts.seating.seats[seat].stack

    # Refund coins
    _refund_player_coins(user_id, refund)

    # Delete Royal21Seat record
    try:
        seat_rec = Royal21Seat.query.filter_by(
            table_id=ts.table_id, user_id=user_id
        ).first()
        if seat_rec:
            db.session.delete(seat_rec)
            db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Failed to delete Royal21Seat for user %s", user_id)

    # Remove from seating and ready sets
    ts.seating.remove_player(seat)
    ts.ready_seats.discard(seat)
    ts.draw_acted_seats.discard(seat)
    if sid:
        ts.remove_player_sid(user_id)
    if sid:
        leave_room(ROOM(ts.table_id), sid=sid)


def _run_showdown(ts: TableState):
    """Evaluate hands, distribute pot, then trigger HAND_END."""
    engine = ts.engine
    if not engine:
        return

    gs = engine.state
    gs.phase = 'SHOWDOWN'
    gs.current_actor = None  # Clear actor to prevent action buttons from showing in SHOWDOWN phase

    # Evaluate all active (non-folded) players' hands
    evaluations = {}
    hand_displays = {}
    for seat, player in gs.players.items():
        if not player.is_folded and player.is_active:
            ev = evaluate_hand(player.hole_cards)
            evaluations[seat] = ev
            from royal21.rules.hand_rankings import hand_display
            hand_displays[seat] = hand_display(player.hole_cards, ev)

    winners = find_winners(evaluations)
    distribution = PotManager.distribute_pot_to_winners(gs, winners)

    # Update stacks
    for seat, chips in distribution.items():
        if seat in gs.players:
            gs.players[seat].stack += chips

    showdown_result = {
        'winners': winners,
        'distribution': distribution,
        'hand_displays': {str(k): v for k, v in hand_displays.items()},
    }

    # Broadcast showdown state
    _broadcast(ts, extra={'showdown_result': showdown_result})

    # Schedule HAND_END (5-second delay to show showdown results)
    socketio.start_background_task(_hand_end_task, ts.table_id)


def _hand_end_task(table_id: int):
    """Background task: wait 5 seconds for showdown display, then process hand end and auto-start if applicable."""
    import time
    time.sleep(5)  # Display showdown results for 5 seconds

    ts = get_table(table_id)
    if not ts or not ts.engine:
        return

    # Sync engine stacks → seating manager
    ts.sync_stacks_to_seating()

    # Remove zero-stack players
    for seat_num in list(ts.seating.get_occupied_seats()):
        if ts.seating.seats[seat_num].stack == 0:
            uid_str = ts.seating.seats[seat_num].player_id
            try:
                uid = int(uid_str)
            except (TypeError, ValueError):
                uid = None
            if uid:
                try:
                    seat_rec = Royal21Seat.query.filter_by(
                        table_id=ts.table_id, user_id=uid
                    ).first()
                    if seat_rec:
                        db.session.delete(seat_rec)
                        db.session.commit()
                except Exception:
                    db.session.rollback()
            ts.seating.remove_player(seat_num)
            ts.player_sids.pop(str(uid), None)

    # Destroy engine; reset ready state for next hand
    ts.engine = None
    ts.draw_acted_seats = set()

    # Determine if we should auto-start the next hand
    occupied_seats = set(ts.seating.get_occupied_seats())
    is_hand_2_plus = ts.hand_number >= 1
    has_2_plus_players = len(occupied_seats) >= 2

    log.info(f"[HAND_END] Table {ts.table_id}: hand_number={ts.hand_number}, occupied_seats={len(occupied_seats)}, auto_start={is_hand_2_plus and has_2_plus_players}")

    # Hand 2+: Auto-start immediately (skip ready screen)
    # Hand 1 or table dropped to 1 player: Show ready screen and wait for players
    if is_hand_2_plus and has_2_plus_players:
        log.info(f"[AUTO-START] Auto-starting hand {ts.hand_number + 1} (was hand {ts.hand_number})")
        try:
            # Start the hand automatically without waiting for ready confirmation
            engine = ts.create_engine()
            button, _card_log = engine.determine_button()
            ts.seating.set_button(button)
            engine.process_antes(ts.ante)
            engine.deal_hand()
            engine.start_betting_round('BETTING_1')
            log.info(f"[AUTO-START] Hand {ts.hand_number} auto-started successfully!")

            # Broadcast game state - hand is now in progress (ANTES phase)
            _broadcast(ts)
        except Exception as e:
            log.error(f"[AUTO-START ERROR] Failed to auto-start: {e}, showing ready screen instead")
            ts.ready_seats = set()
            _broadcast(ts, extra={'phase': 'HAND_END'})
    else:
        # Insufficient players: Show ready screen
        log.info(f"[HAND_END] Showing ready screen for hand {ts.hand_number + 1} (is_hand_2_plus={is_hand_2_plus}, has_2_plus_players={has_2_plus_players})")
        ts.ready_seats = set()
        _broadcast(ts, extra={'phase': 'HAND_END'})


def _check_phase_advance(ts: TableState):
    """
    After an action, check whether the current phase is complete and advance.
    Called after every processed action.
    """
    engine = ts.engine
    if not engine:
        return

    gs = engine.state

    # ---- One active player left → hand over ----
    active = gs.get_active_players()
    if len(active) == 1 and gs.phase in ('BETTING_1', 'BETTING_2'):
        winner_seat = active[0]
        gs.players[winner_seat].stack += gs.pot.main_pot + sum(
            p.current_bet for p in gs.players.values()
        )
        gs.pot.main_pot = 0
        for p in gs.players.values():
            p.current_bet = 0
        gs.phase = 'SHOWDOWN'
        showdown_result = {
            'winners': [winner_seat],
            'distribution': {winner_seat: gs.players[winner_seat].stack},
            'hand_displays': {},
        }
        _broadcast(ts, extra={'showdown_result': showdown_result})
        socketio.start_background_task(_hand_end_task, ts.table_id)
        return

    phase = gs.phase

    if phase == 'BETTING_1':
        # Round complete when all active players have equal bets and current_actor advanced back
        if gs.current_actor is None or BettingCalculator.is_betting_round_complete(gs):
            _collect_bets(engine)
            engine.start_draw_phase()
            ts.draw_acted_seats = set()
            _broadcast(ts)
        else:
            _broadcast(ts)

    elif phase == 'DRAW':
        # Check if all non-folded, non-busted players have acted
        eligible = [
            s for s, p in gs.players.items()
            if not p.is_folded and p.is_active and not p.is_bust
        ]
        if all(s in ts.draw_acted_seats for s in eligible):
            engine.start_betting_round('BETTING_2')
            _broadcast(ts)
        else:
            # Auto-advance past busted players
            _advance_draw_actor(ts)
            _broadcast(ts)

    elif phase == 'BETTING_2':
        if gs.current_actor is None or BettingCalculator.is_betting_round_complete(gs):
            _collect_bets(engine)
            _run_showdown(ts)
        else:
            _broadcast(ts)

    else:
        _broadcast(ts)


def _advance_draw_actor(ts: TableState):
    """Find next actor in DRAW phase who hasn't acted yet and isn't busted."""
    engine = ts.engine
    if not engine:
        return
    gs = engine.state
    # Walk from current actor to find next eligible player
    current = gs.current_actor
    for _ in range(7):
        nxt = gs.get_next_actor_after(current)
        if nxt is None:
            gs.current_actor = None
            return
        p = gs.players.get(nxt)
        if p and not p.is_folded and p.is_active and not p.is_bust and nxt not in ts.draw_acted_seats:
            gs.current_actor = nxt
            return
        current = nxt
    gs.current_actor = None


# ---------------------------------------------------------------------------
# SocketIO event registration
# ---------------------------------------------------------------------------

def _register_socketio_events(sio):

    @sio.on('royal21_join')
    def on_join(data):
        if not current_user.is_authenticated:
            emit('royal21_error', {'message': 'Not authenticated'})
            return

        table_id = int(data.get('table_id', 0))
        buyin = int(data.get('buyin', 0))
        requested_seat = data.get('seat')  # Optional: specific seat

        # Validate table
        table_rec = Royal21Table.query.get(table_id)
        if not table_rec or not table_rec.is_open:
            emit('royal21_error', {'message': 'Table not found or closed'})
            return

        # Check if user already seated at this table
        existing = Royal21Seat.query.filter_by(
            table_id=table_id, user_id=current_user.id
        ).first()
        if existing:
            emit('royal21_error', {'message': 'Already seated at this table'})
            return

        # Validate buy-in
        if buyin < table_rec.min_buyin or buyin > table_rec.max_buyin:
            emit('royal21_error', {
                'message': f'Buy-in must be between {table_rec.min_buyin} and {table_rec.max_buyin}'
            })
            return
        if int(current_user.coins) < buyin:
            emit('royal21_error', {'message': 'Insufficient coins'})
            return

        # Find seat
        ts = get_or_create_table(table_id, table_rec.ante, table_rec.min_buyin, table_rec.max_buyin)

        if ts.seating.is_full():
            emit('royal21_error', {'message': 'Table is full'})
            return

        if requested_seat is not None:
            seat_num = int(requested_seat)
            if ts.seating.seats[seat_num].player_id is not None:
                emit('royal21_error', {'message': 'Seat is taken'})
                return
        else:
            available = ts.get_available_seats()
            if not available:
                emit('royal21_error', {'message': 'No seats available'})
                return
            seat_num = available[0]

        # Deduct coins
        try:
            current_user.coins = int(current_user.coins) - buyin
            seat_rec = Royal21Seat(
                table_id=table_id,
                seat_number=seat_num,
                user_id=current_user.id,
                coins_escrowed=buyin,
            )
            db.session.add(seat_rec)
            db.session.commit()
        except Exception:
            db.session.rollback()
            emit('royal21_error', {'message': 'Failed to join table'})
            return

        # Add to seating manager
        ts.seating.assign_player(seat_num, current_user.username, str(current_user.id), buyin)

        # Join SocketIO room and track SID
        join_room(ROOM(table_id))
        ts.add_player_sid(current_user.id, request.sid)

        _broadcast(ts)

    @sio.on('royal21_ready')
    def on_ready(data):
        if not current_user.is_authenticated:
            return

        table_id = int(data.get('table_id', 0))
        ts = get_table(table_id)
        if not ts:
            emit('royal21_error', {'message': 'Table not found'})
            return

        seat = ts.get_player_seat(current_user.id)
        if seat is None:
            emit('royal21_error', {'message': 'Not seated at this table'})
            return

        if ts.engine:
            emit('royal21_error', {'message': 'Hand already in progress'})
            return

        ts.ready_seats.add(seat)

        # Check if we should start the hand
        # For hand 1: Require explicit ready from all players
        # For hand 2+: Auto-start as soon as all seated players have confirmed ready
        should_start = False
        if ts.hand_number <= 1:
            # First hand: Start only when explicitly all players are ready
            should_start = ts.all_seated_ready()
        else:
            # Subsequent hands: Auto-start as soon as all seated players are ready
            # (they may have been auto-populated at hand end)
            should_start = ts.all_seated_ready()

        if should_start:
            # Start the hand
            engine = ts.create_engine()
            button, _card_log = engine.determine_button()
            ts.seating.set_button(button)
            engine.process_antes(ts.ante)
            engine.deal_hand()
            engine.start_betting_round('BETTING_1')

        _broadcast(ts)

    @sio.on('royal21_action')
    def on_action(data):
        if not current_user.is_authenticated:
            return

        table_id = int(data.get('table_id', 0))
        action_type = data.get('action_type', '')
        amount = data.get('amount')
        if amount is not None:
            amount = int(amount)
        card_index = data.get('card_index')
        if card_index is not None:
            card_index = int(card_index)

        ts = get_table(table_id)
        if not ts or not ts.engine:
            emit('royal21_error', {'message': 'No active game'})
            return

        seat = ts.get_player_seat(current_user.id)
        if seat is None:
            emit('royal21_error', {'message': 'Not seated at this table'})
            return

        engine = ts.engine
        gs = engine.state

        # Process action
        ok = engine.process_action(seat, action_type, amount, card_index)
        if not ok:
            emit('royal21_error', {'message': 'Invalid action'})
            return

        # If reveal: just broadcast and return (no phase change)
        if action_type == 'reveal':
            _broadcast(ts)
            return

        # Track draw actions
        if gs.phase == 'DRAW':
            ts.draw_acted_seats.add(seat)

        # Advance actor for non-reveal actions
        if action_type not in ('reveal',):
            engine.advance_to_next_actor()

        _check_phase_advance(ts)

    @sio.on('royal21_leave')
    def on_leave(data):
        if not current_user.is_authenticated:
            return

        table_id = int(data.get('table_id', 0))
        ts = get_table(table_id)
        if not ts:
            return

        _remove_player_from_table(ts, current_user.id, sid=request.sid)
        _broadcast(ts)

    @sio.on('royal21_get_state')
    def on_get_state(data):
        """Called on page load / reconnect to get current table state."""
        if not current_user.is_authenticated:
            emit('royal21_error', {'message': 'Not authenticated'})
            return

        table_id = int(data.get('table_id', 0))
        existing = Royal21Seat.query.filter_by(
            table_id=table_id, user_id=current_user.id
        ).first()

        if not existing:
            emit('royal21_no_seat', {})
            return

        table_rec = Royal21Table.query.get(table_id)
        if not table_rec:
            emit('royal21_error', {'message': 'Table not found'})
            return

        ts = get_or_create_table(table_id, table_rec.ante, table_rec.min_buyin, table_rec.max_buyin)
        seat_in_memory = ts.get_player_seat(current_user.id)

        if seat_in_memory is None:
            # Server restarted: refund escrow and clear seat
            _refund_player_coins(current_user.id, existing.coins_escrowed)
            try:
                db.session.delete(existing)
                db.session.commit()
            except Exception:
                db.session.rollback()
            emit('royal21_no_seat', {})
            return

        # Reconnect: re-join room and emit current state
        join_room(ROOM(table_id))
        ts.add_player_sid(current_user.id, request.sid)
        priv = _build_state(ts, viewing_seat=seat_in_memory)
        emit('royal21_private', priv)

    @sio.on('disconnect')
    def on_disconnect():
        if not current_user.is_authenticated:
            return
        for tid in all_table_ids():
            ts = get_table(tid)
            if ts and ts.get_player_seat(current_user.id) is not None:
                _remove_player_from_table(ts, current_user.id, sid=request.sid)
                _broadcast(ts)
