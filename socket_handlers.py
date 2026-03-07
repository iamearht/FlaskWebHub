"""
Socket.IO event handlers for real-time game communication.

Replaces polling-based HTTP REST API with event-driven Socket.IO communication
for both classic/interactive game modes and free blackjack mode.
"""

from flask import request, session
from flask_socketio import (
    emit, join_room, leave_room, disconnect, rooms
)
from flask_login import current_user
from extensions import db
from models import Match, User
from engine import (
    get_client_state, check_timeout, apply_timeout,
    do_card_draw, make_choice, place_bets, handle_insurance,
    player_action as engine_player_action,
    dealer_action as engine_dealer_action,
    assign_joker_values, assign_dealer_joker_values,
    next_round_or_end_turn
)

# Game session tracking: {match_id: {player_sid, ...}, ...}
GAME_SESSIONS = {}
BLACKJACK_SESSIONS = {}


def init_socket(socketio):
    """Initialize Socket.IO event handlers."""

    # ===================================================================
    # CLASSIC GAME MODES (Database-backed)
    # ===================================================================

    @socketio.on('connect', namespace='/game/classic')
    def on_classic_connect():
        """Handle player connection to classic game mode."""
        if not current_user.is_authenticated:
            return False

        emit('connected', {
            'user_id': current_user.id,
            'username': current_user.username,
        })

    @socketio.on('join_game', namespace='/game/classic')
    def on_classic_join_game(data):
        """Join a specific game match."""
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return

        match_id = data.get('match_id')
        if not match_id:
            emit('error', {'message': 'match_id required'})
            return

        match = db.session.get(Match, match_id)
        if not match:
            emit('error', {'message': 'Match not found'})
            return

        # Verify user is participant
        if match.player1_id != current_user.id and match.player2_id != current_user.id:
            emit('error', {'message': 'Not a participant in this match'})
            return

        # Join socket room for this match
        join_room(f'match_{match_id}')

        # Track session
        if match_id not in GAME_SESSIONS:
            GAME_SESSIONS[match_id] = set()
        GAME_SESSIONS[match_id].add(request.sid)

        # Send initial game state
        state = get_client_state(match, current_user.id)
        emit('game_state', state)

    @socketio.on('player_action', namespace='/game/classic')
    def on_classic_player_action(data):
        """Handle player game action (hit, stand, bet, etc.)."""
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return

        match_id = data.get('match_id')
        action_type = data.get('action')

        if not match_id or not action_type:
            emit('error', {'message': 'match_id and action required'})
            return

        match = db.session.get(Match, match_id)
        if not match:
            emit('error', {'message': 'Match not found'})
            return

        # Verify user is participant
        if match.player1_id != current_user.id and match.player2_id != current_user.id:
            emit('error', {'message': 'Not a participant in this match'})
            return

        # FIX BUG #2: Move socketio_emit import outside try block for better error handling
        from flask_socketio import emit as socketio_emit

        # FIX BUG #4: Verify socket is in the game room
        if f'match_{match_id}' not in rooms():
            join_room(f'match_{match_id}')

        try:
            # Determine correct player number for this user (FIX BUG #1)
            if match.player1_id == current_user.id:
                user_player_num = 1
            else:
                user_player_num = 2

            # Apply any overdue automatic actions BEFORE proceeding
            while check_timeout(match):
                apply_timeout(match)
                # FIX BUG #3/5: Broadcast state after each timeout action, not just at the end
                db.session.commit()
                state = get_client_state(match, user_player_num)
                socketio_emit('game_state', state, room=f'match_{match_id}', namespace='/game/classic')

            # Process action based on type
            if action_type == 'draw':
                do_card_draw(match)
            elif action_type == 'choice':
                goes_first = bool(data.get('go_first_as_player', False))
                print(f"\n[CHOICE DEBUG] Player {user_player_num} choosing: goes_first_as_player={goes_first}")
                print(f"[CHOICE DEBUG] match.player1_id={match.player1_id}, match.player2_id={match.player2_id}")

                # Get current state before choice
                from models import MatchState
                ms_before = MatchState.query.filter_by(match_id=match_id).first()
                print(f"[CHOICE DEBUG] Before: phase={ms_before.phase if ms_before else 'N/A'}")

                make_choice(match, goes_first)
                db.session.commit()

                # Get state after choice
                ms_after = MatchState.query.filter_by(match_id=match_id).first()
                print(f"[CHOICE DEBUG] After make_choice: phase={ms_after.phase}, choice_made={ms_after.choice_made}")
                if ms_after.current_turn < len(match.turns):
                    turn = match.turns[ms_after.current_turn]
                    print(f"[CHOICE DEBUG] Turn 0: player_role={turn.player_role}, dealer_role={turn.dealer_role}")

                # Calculate and log states
                state_p1 = get_client_state(match, 1)
                state_p2 = get_client_state(match, 2)
                print(f"[CHOICE DEBUG] State P1: is_my_turn={state_p1.get('is_my_turn')}, phase={state_p1.get('phase')}")
                print(f"[CHOICE DEBUG] State P2: is_my_turn={state_p2.get('is_my_turn')}, phase={state_p2.get('phase')}")

                # Broadcast - FIX BUG #6: Broadcast choice action with each player's perspective
                socketio_emit('game_state', state_p1, room=f'match_{match_id}', namespace='/game/classic', skip_sid=request.sid)
                print(f"[CHOICE DEBUG] Broadcasted state_p1 (skip_sid={request.sid})")

                socketio_emit('game_state', state_p2, room=f'match_{match_id}', namespace='/game/classic', skip_sid=request.sid)
                print(f"[CHOICE DEBUG] Broadcasted state_p2 (skip_sid={request.sid})")

                # Send requesting player their response
                state_requester = get_client_state(match, user_player_num)
                emit('game_state', state_requester)
                print(f"[CHOICE DEBUG] Sent state to requester (P{user_player_num})\n")
                return  # Skip generic broadcast below
            elif action_type == 'bet':
                bets = data.get('bets', [])
                place_bets(match, bets)
            elif action_type == 'insurance':
                decisions = data.get('decisions', [])
                handle_insurance(match, decisions)
            elif action_type in ['hit', 'stand', 'double', 'split']:
                # Player action with action type
                engine_player_action(match, action_type)
            elif action_type.startswith('dealer_action_'):
                # Dealer action (dealer_action_hit, dealer_action_stand)
                dealer_action_name = action_type.split('_', 2)[2]  # Extract 'hit' or 'stand'
                engine_dealer_action(match, dealer_action_name)
            elif action_type == 'joker':
                values = data.get('values', [])
                assign_joker_values(match, values)
            elif action_type == 'dealer_joker':
                values = data.get('values', [])
                assign_dealer_joker_values(match, values)
            elif action_type == 'next_round':
                next_round_or_end_turn(match)
            else:
                emit('error', {'message': f'Unknown action type: {action_type}'})
                return

            # Commit changes
            db.session.commit()

            # Broadcast updated state to all players (FIX BUG #1: Pass correct player_num instead of None)
            state = get_client_state(match, user_player_num)
            socketio_emit('game_state', state, room=f'match_{match_id}', namespace='/game/classic')

        except ValueError as e:
            db.session.rollback()
            emit('error', {'message': str(e)})
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            emit('error', {'message': 'Internal server error'})

    @socketio.on('get_state', namespace='/game/classic')
    def on_classic_get_state(data):
        """Request current game state."""
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return

        match_id = data.get('match_id')
        match = db.session.get(Match, match_id)
        if not match:
            emit('error', {'message': 'Match not found'})
            return

        state = get_client_state(match, current_user.id)
        emit('game_state', state)

    @socketio.on('disconnect', namespace='/game/classic')
    def on_classic_disconnect():
        """Handle player disconnect."""
        # Clean up room tracking
        for match_id, sids in list(GAME_SESSIONS.items()):
            if request.sid in sids:
                sids.discard(request.sid)
                if not sids:
                    del GAME_SESSIONS[match_id]

    # ===================================================================
    # FREE BLACKJACK MODE (In-memory)
    # ===================================================================

    @socketio.on('connect', namespace='/game/blackjack')
    def on_blackjack_connect():
        """Handle player connection to blackjack game mode."""
        if not current_user.is_authenticated:
            return False

        emit('connected', {
            'user_id': current_user.id,
            'username': current_user.username,
        })

    @socketio.on('join_table', namespace='/game/blackjack')
    def on_blackjack_join_table(data):
        """Join a blackjack table."""
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return

        table_id = data.get('table_id')
        seat = data.get('seat')

        if not table_id:
            emit('error', {'message': 'table_id required'})
            return

        try:
            from blackjack_game_bp import TABLES
            from flask_socketio import emit as socketio_emit

            if table_id not in TABLES:
                emit('error', {'message': 'Table not found'})
                return

            engine = TABLES[table_id]

            # Join socket room for this table
            join_room(f'blackjack_table_{table_id}')

            # Track session
            if table_id not in BLACKJACK_SESSIONS:
                BLACKJACK_SESSIONS[table_id] = set()
            BLACKJACK_SESSIONS[table_id].add(request.sid)

            # Send initial table state
            state = engine.get_state()
            emit('table_state', state)

            # Notify other players
            socketio_emit('player_joined', {
                'user_id': current_user.id,
                'username': current_user.username,
                'seat': seat,
            }, room=f'blackjack_table_{table_id}', skip_sid=request.sid, namespace='/game/blackjack')

        except Exception as e:
            import traceback
            traceback.print_exc()
            emit('error', {'message': str(e)})

    @socketio.on('table_action', namespace='/game/blackjack')
    def on_blackjack_table_action(data):
        """Handle player action at blackjack table."""
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return

        table_id = data.get('table_id')
        action_name = data.get('action')
        seat = data.get('seat')

        if not table_id or not action_name or seat is None:
            emit('error', {'message': 'table_id, action, and seat required'})
            return

        try:
            from blackjack_game_bp import TABLES
            from blackjack_game_engine import ActionType
            from flask_socketio import emit as socketio_emit

            if table_id not in TABLES:
                emit('error', {'message': 'Table not found'})
                return

            engine = TABLES[table_id]

            # Verify user is the player at this seat
            player = next((p for p in engine.game_state.players if p.seat == seat), None)
            if not player or player.player_id != current_user.id:
                emit('error', {'message': 'Not your seat'})
                return

            # Parse action and execute
            action = ActionType[action_name.upper()]
            amount = int(data.get('amount', 0))
            card_index = data.get('card_index')
            if card_index is not None:
                card_index = int(card_index)

            engine.player_action(seat, action, amount, card_index=card_index)

            # Broadcast updated table state to all players at this table
            state = engine.get_state()
            socketio_emit('table_state', state, room=f'blackjack_table_{table_id}', namespace='/game/blackjack')

        except KeyError:
            emit('error', {'message': f'Unknown action: {action_name}'})
        except ValueError as e:
            emit('error', {'message': str(e)})
        except Exception as e:
            import traceback
            traceback.print_exc()
            emit('error', {'message': 'Internal server error'})

    @socketio.on('get_table_state', namespace='/game/blackjack')
    def on_blackjack_get_table_state(data):
        """Request current table state."""
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return

        table_id = data.get('table_id')

        try:
            from blackjack_game_bp import TABLES

            if table_id not in TABLES:
                emit('error', {'message': 'Table not found'})
                return

            engine = TABLES[table_id]
            state = engine.get_state()
            emit('table_state', state)
        except Exception as e:
            import traceback
            traceback.print_exc()
            emit('error', {'message': str(e)})

    @socketio.on('disconnect', namespace='/game/blackjack')
    def on_blackjack_disconnect():
        """Handle player disconnect from blackjack table."""
        # Clean up room tracking
        for table_id, sids in list(BLACKJACK_SESSIONS.items()):
            if request.sid in sids:
                sids.discard(request.sid)
                if not sids:
                    del BLACKJACK_SESSIONS[table_id]
