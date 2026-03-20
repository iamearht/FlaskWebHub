"""Game engine - fresh implementation starting with button determination."""

import random
from typing import Optional
from .card import Card
from .deck import Deck
from .game_state import GameState, PlayerState
from .betting import BettingCalculator


class GameEngine:
    """Game engine focused on button determination."""

    def __init__(self, table_id: str, game_id: str, ante: int, seating):
        """Initialize the game engine."""
        self.table_id = table_id
        self.game_id = game_id
        self.ante = ante
        self.seating = seating
        self.state = GameState()
        self._populate_players_from_seating()

    def _populate_players_from_seating(self):
        """Populate game state with players from seating manager."""
        for seat_num in range(7):
            seat = self.seating.get_seat(seat_num)
            if seat and seat.player_id:
                self.state.add_player(seat_num, seat.player_name, seat.player_id, seat.stack)

    def determine_button(self) -> tuple[int, list]:
        """
        Determine the button position.

        Deals one card to each seated player. Highest card gets button.
        Ties are broken by redrawing (only tied players).

        Returns:
            Tuple of (button_seat, card_log) where card_log contains the sequence of events
        """
        seated_seats = self.state.get_seated_players()
        card_log = []  # Track all card deals and events for display

        if len(seated_seats) < 2:
            # Shouldn't happen based on requirements, but handle gracefully
            return (seated_seats[0] if seated_seats else 0, card_log)

        remaining_seats = seated_seats[:]
        dealt_cards = {}  # {seat: card}

        while len(remaining_seats) > 1:
            # Deal one card to each remaining player
            for seat in remaining_seats:
                card = self.state.deck.draw()
                dealt_cards[seat] = card
                player_name = self.state.get_player_name(seat)

                # Log this card deal
                card_log.append({
                    "type": "card_dealt",
                    "seat": seat,
                    "player_name": player_name,
                    "card": card.display
                })

            # Find highest card(s)
            max_value = max(dealt_cards[s].value for s in remaining_seats)
            highest_seats = [s for s in remaining_seats if dealt_cards[s].value == max_value]

            if len(highest_seats) == 1:
                # Winner found
                button = highest_seats[0]
                self.state.button_seat = button
                break
            else:
                # Tie - only these players redraw
                tie_message = f"Tie! Seats {highest_seats} redraw..."
                card_log.append({
                    "type": "tiebreaker",
                    "seats": highest_seats,
                    "message": tie_message
                })
                remaining_seats = highest_seats
                dealt_cards.clear()

        # Put all dealt cards back and reshuffle
        all_dealt = [dealt_cards[s] for s in dealt_cards.keys()]
        self.state.deck.reshuffle_with(all_dealt)

        button = self.state.button_seat

        return (button, card_log)

    def get_game_state(self, viewing_player_seat: int = None) -> dict:
        """Return current game state as dictionary.

        Args:
            viewing_player_seat: The seat number of the player viewing this state.
                                Only this player will see their own hole_cards.
                                If None, all hole_cards are hidden for privacy.
        """
        state = {
            "phase": self.state.phase,
            "button_seat": self.state.button_seat,
            "hand_number": self.state.hand_number,
            "pot": self.state.pot.main_pot,
            "current_high_bet": self.state.current_high_bet,
            "current_actor": self.state.current_actor,
            "players": {
                seat: {
                    "name": player.name,
                    "stack": player.stack,
                    "chips_in_pot": player.chips_in_pot,
                    "current_bet": player.current_bet,
                    "is_folded": player.is_folded,
                    "is_all_in": player.is_all_in,
                    "is_active": player.is_active,
                    # Only show hole_cards to the player who owns them
                    "hole_cards": (
                        [c.display if c else "?" for c in player.hole_cards]
                        if player.hole_cards else []
                    ) if (viewing_player_seat == seat) else [],
                    # Show revealed card to all players
                    "exposed_card": (
                        self.get_player_exposed_card(seat).display
                        if self.get_player_exposed_card(seat) else None
                    ),
                    "has_acted_preflop": player.has_acted_preflop,
                    "hand_value": player.calculate_hand_value(),
                    "is_bust": player.is_bust,
                }
                for seat, player in self.state.players.items()
            },
        }

        # Add legal actions for current actor if they exist
        if self.state.current_actor is not None:
            state["legal_actions"] = self.get_legal_actions(self.state.current_actor)
        else:
            state["legal_actions"] = []

        return state

    def get_player_seat(self, player_id: str) -> Optional[int]:
        """Get the seat number for a given player_id.

        Args:
            player_id: The player's unique ID

        Returns:
            The seat number (0-6) or None if player not found
        """
        for seat, player in self.state.players.items():
            if player.player_id == player_id:
                return seat
        return None

    def process_antes(self, ante_amount: int) -> None:
        """Deduct antes from all players.

        Everyone antes once, button antes double.

        Args:
            ante_amount: Amount each player antes
        """
        self.state.phase = "ANTES"
        self.state.button_big_blind = ante_amount  # Track the big blind amount

        for seat, player in self.state.players.items():
            # Everyone antes once
            player.stack -= ante_amount
            player.chips_in_pot += ante_amount
            self.state.pot.main_pot += ante_amount

        # Button posts big blind (not added to main pot, stays as pending bet)
        button = self.state.button_seat
        if button in self.state.players:
            self.state.players[button].stack -= ante_amount
            self.state.players[button].chips_in_pot += ante_amount
            # IMPORTANT: Don't add to main_pot - this is a pending bet until others match it
            self.state.players[button].current_bet = ante_amount  # Track as pending bet

    def deal_hand(self) -> None:
        """Deal 2 hole cards to each seated player.

        Shuffles deck and deals face-down cards (hidden from other players).
        """
        self.state.phase = "DEAL"
        self.state.deck.shuffle()

        for seat in self.state.get_seated_players():
            player = self.state.players[seat]
            card1 = self.state.deck.draw()
            card2 = self.state.deck.draw()
            player.hole_cards = [card1, card2]

    def start_betting_round(self, phase: str = "BETTING_1") -> None:
        """Initialize a betting round.

        Args:
            phase: "BETTING_1" (preflop with blinds) or "BETTING_2" (POST with no blinds)

        Sets up:
        - Phase = specified phase
        - Current actor = first after button (UTG)
        - Current high bet = button's big blind (BETTING_1) or 0 (BETTING_2)
        - Reset action tracking for all players
        """
        self.state.phase = phase

        if phase == "BETTING_1":
            self.state.current_high_bet = self.state.button_big_blind
        else:  # BETTING_2
            self.state.current_high_bet = 0

        # Reset action tracking for all players at start of betting round
        for player in self.state.players.values():
            if player:
                player.has_acted_on_current_bet = False

        # Find first to act (next occupied seat after button) - same for both phases
        first_actor = self.state.get_next_actor_after(self.state.button_seat)
        self.state.current_actor = first_actor

    def start_draw_phase(self) -> None:
        """Initialize draw phase where players decide to HIT or STAND.

        Sets up:
        - Phase = DRAW
        - Current actor = first after button (UTG)
        - Reset current_bet for all players (draw has no betting)
        """
        self.state.phase = "DRAW"

        # Find first to act (UTG - same as BETTING_1)
        first_actor = self.state.get_next_actor_after(self.state.button_seat)
        self.state.current_actor = first_actor

        # Reset current_bet for all players since draw phase has no betting
        for player in self.state.players.values():
            player.current_bet = 0

    def get_legal_actions(self, seat: int) -> list[dict]:
        """Get available actions for a player.

        Args:
            seat: Player's seat number

        Returns:
            List of legal action dicts with action type and parameters
        """
        # No actions available in non-betting phases
        if self.state.phase not in ["BETTING_1", "BETTING_2", "DRAW"]:
            return []

        if seat not in self.state.players or seat != self.state.current_actor:
            return []

        player = self.state.players[seat]
        if player.is_folded or not player.is_active:
            return []

        # DRAW phase: all-in players CAN still HIT/STAND (they have a live hand)
        if self.state.phase == "DRAW":
            if player.is_bust:
                # Busted players have no legal actions (auto-advance)
                return []
            # All active non-busted players (including all-in) can HIT or STAND
            return [
                {"action": "hit"},
                {"action": "stand"}
            ]

        # BETTING phases: all-in players are auto-skipped (no actions available)
        if player.is_all_in or player.stack == 0:
            return []

        call_amount = BettingCalculator.get_call_amount(self.state, seat)

        # Partial call: player can't fully match the bet — offer all-in call only
        if call_amount > 0 and player.stack < call_amount:
            return [
                {"action": "fold"},
                {"action": "call", "amount": player.stack, "is_all_in": True},
            ]

        actions = []

        # Check if button's special case (checking their own big blind) - PREFLOP only
        # POST phase (BETTING_2) has no special button mechanics
        is_button_check_case = (self.state.phase == "BETTING_1" and
                                 seat == self.state.button_seat and
                                 call_amount == self.state.button_big_blind and
                                 call_amount > 0)

        if is_button_check_case:
            # Button checks their own blind (no additional cost)
            # No fold option when checking their own blind
            actions.append({"action": "check"})

            # Button can also raise from their blind
            last_raise_size = self.state.current_high_bet
            min_raise = BettingCalculator.get_min_raise(last_raise_size, self.state.current_high_bet)
            max_raise = BettingCalculator.get_max_raise(self.state, seat, last_raise_size)

            if max_raise >= min_raise:
                actions.append({
                    "action": "raise",
                    "min": min_raise,
                    "max": max_raise
                })
        elif call_amount == 0:
            # Can check or bet
            actions.append({"action": "check"})

            if self.state.current_high_bet > 0:
                # Prior bet exists (e.g. player matched the blind) — use P+3B formula
                max_bet = BettingCalculator.get_max_raise(
                    self.state, seat, self.state.current_high_bet
                )
            else:
                # Truly first to open — no prior bet, use pot-only formula
                max_bet = BettingCalculator.get_max_bet_no_raise(self.state)
            # Min raise: at least one full blind size above current high bet
            # BETTING_1 (current_high_bet=1): min = max(1, 1+1) = 2
            # BETTING_2 (current_high_bet=0): min = max(1, 0+0) = 1
            min_bet = max(1, BettingCalculator.get_min_raise(
                self.state.current_high_bet, self.state.current_high_bet
            ))
            if max_bet >= min_bet:
                actions.append({
                    "action": "raise",
                    "min": min_bet,
                    "max": max_bet
                })
        else:
            # Must call, fold, or raise
            actions.append({"action": "fold"})
            actions.append({
                "action": "call",
                "amount": call_amount
            })

            # Can raise (pot limit)
            last_raise_size = self.state.current_high_bet  # Initial: use big blind as last raise
            min_raise = BettingCalculator.get_min_raise(last_raise_size, self.state.current_high_bet)
            max_raise = BettingCalculator.get_max_raise(self.state, seat, last_raise_size)

            if max_raise >= min_raise:
                actions.append({
                    "action": "raise",
                    "min": min_raise,
                    "max": max_raise
                })

        return actions

    def process_action(self, seat: int, action_type: str, amount: Optional[int] = None, card_index: Optional[int] = None) -> bool:
        """Process a betting action or card reveal.

        Args:
            seat: Player's seat
            action_type: "fold", "check", "call", "raise", "reveal"
            amount: Bet amount for raise actions
            card_index: Card index (0 or 1) for reveal actions

        Returns:
            True if action was valid and processed, False otherwise
        """
        if seat not in self.state.players:
            return False

        player = self.state.players[seat]

        # Handle reveal action (doesn't require being current actor)
        if action_type == "reveal":
            if card_index is None or card_index not in [0, 1]:
                return False
            if self.set_exposed_card_index(seat, card_index) is None:
                return False
            return True

        # Handle draw phase actions (HIT, STAND)
        if self.state.phase == "DRAW":
            if action_type not in ["hit", "stand"]:
                return False
            # Draw actions require being current actor
            if seat != self.state.current_actor:
                return False
            return self.handle_draw_action(seat, action_type)

        # Other actions require being current actor
        if seat != self.state.current_actor:
            return False

        # Validate action
        call_amount = BettingCalculator.get_call_amount(self.state, seat)

        if action_type == "fold":
            player.is_folded = True
            player.is_active = False
            # Mark as acted if in PREFLOP
            if self.state.phase == "BETTING_1":
                player.has_acted_preflop = True
            # Mark as acted on current bet
            if self.state.phase in ("BETTING_1", "BETTING_2"):
                player.has_acted_on_current_bet = True
            return True

        elif action_type == "check":
            if call_amount != 0:
                return False  # Can't check if someone bet
            # Mark as acted if in PREFLOP
            if self.state.phase == "BETTING_1":
                player.has_acted_preflop = True
            # Mark as acted on current bet
            if self.state.phase in ("BETTING_1", "BETTING_2"):
                player.has_acted_on_current_bet = True
            return True

        elif action_type == "call":
            if call_amount == 0:
                return False  # Can't call if nothing to call

            # Allow partial calls: player goes all-in with whatever they have left
            actual_call = min(call_amount, player.stack)
            player.stack -= actual_call
            player.current_bet += actual_call
            player.chips_in_pot += actual_call
            # NOTE: Do NOT add to main_pot here - bets stay as pending (current_bet)
            # They will be moved to main_pot at the end of the betting round

            # Check if all-in
            if player.stack == 0:
                player.is_all_in = True

            # Mark as acted if in PREFLOP
            if self.state.phase == "BETTING_1":
                player.has_acted_preflop = True
            # Mark as acted on current bet
            if self.state.phase in ("BETTING_1", "BETTING_2"):
                player.has_acted_on_current_bet = True

            return True

        elif action_type == "raise":
            if amount is None:
                return False

            # Validate raise amount
            last_raise_size = self.state.current_high_bet  # For min raise calculation
            min_raise = BettingCalculator.get_min_raise(last_raise_size, self.state.current_high_bet)
            max_raise = BettingCalculator.get_max_raise(self.state, seat, last_raise_size)

            if amount < min_raise or amount > max_raise:
                return False  # Invalid raise amount

            amount_to_add = amount - player.current_bet
            if player.stack < amount_to_add:
                return False  # Not enough chips

            player.stack -= amount_to_add
            player.current_bet = amount
            player.chips_in_pot += amount_to_add
            # NOTE: Do NOT add to main_pot here - bets stay as pending (current_bet)
            # They will be moved to main_pot at the end of the betting round

            # Update high bet
            old_high_bet = self.state.current_high_bet
            self.state.current_high_bet = amount

            # Check if all-in
            if player.stack == 0:
                player.is_all_in = True

            # Mark as acted if in PREFLOP
            if self.state.phase == "BETTING_1":
                player.has_acted_preflop = True
            # Mark as acted on current bet
            if self.state.phase in ("BETTING_1", "BETTING_2"):
                player.has_acted_on_current_bet = True
                # Reset other players' action tracking since bet level increased
                for other_seat, other_player in self.state.players.items():
                    if other_seat != seat and other_player:
                        other_player.has_acted_on_current_bet = False

            return True

        return False

    def handle_draw_action(self, seat: int, action_type: str) -> bool:
        """Process a HIT or STAND action in the draw phase.

        Args:
            seat: Player's seat
            action_type: "hit" or "stand"

        Returns:
            True if action was valid and processed, False otherwise
        """
        if seat not in self.state.players:
            return False

        player = self.state.players[seat]

        # Validate that player can act
        if player.is_folded or not player.is_active or player.is_bust:
            return False

        if action_type == "hit":
            # Draw one card from deck
            new_card = self.state.deck.draw()
            player.hole_cards.append(new_card)

            # Check if player busts
            player.check_bust()

            return True

        elif action_type == "stand":
            # Player keeps current hand, no card drawn
            return True

        return False

    def advance_to_next_actor(self) -> bool:
        """Move to next player to act.

        In DRAW phase, automatically skip busted players.

        Returns:
            False if betting round is complete, True if continuing
        """
        current = self.state.current_actor
        if current is None:
            return False

        next_actor = self.state.get_next_actor_after(current)

        # In DRAW phase, skip busted players
        while next_actor is not None and self.state.phase == "DRAW":
            if self.state.players[next_actor].is_bust:
                # Player is bust, skip to next
                next_actor = self.state.get_next_actor_after(next_actor)
            else:
                # Found a non-busted player
                break

        # In BETTING phases, skip all-in players (with loop protection)
        visited: set = set()
        while next_actor is not None and self.state.phase in ("BETTING_1", "BETTING_2"):
            if next_actor in visited:
                next_actor = None  # All remaining non-folded players are all-in — round done
                break
            player = self.state.players.get(next_actor)
            if player and player.is_all_in:
                visited.add(next_actor)
                next_actor = self.state.get_next_actor_after(next_actor)
            else:
                break

        self.state.current_actor = next_actor

        return next_actor is not None

    def get_phase(self) -> str:
        """Get current game phase."""
        return self.state.phase

    def get_active_player_count(self) -> int:
        """Get number of players still in hand."""
        return len([p for p in self.state.players.values() if p.is_active and not p.is_folded])

    def set_exposed_card_index(self, seat: int, card_index: int) -> Optional[Card]:
        """Record which card player chose to reveal.

        Args:
            seat: Player's seat number
            card_index: Index of card to reveal (0 or 1)

        Returns:
            The Card object that was revealed, or None if invalid
        """
        if seat not in self.state.players or card_index not in [0, 1]:
            return None

        player = self.state.players[seat]
        if not player.hole_cards or card_index >= len(player.hole_cards):
            return None

        player.exposed_card_index = card_index
        return player.hole_cards[card_index]

    def get_player_exposed_card(self, seat: int) -> Optional[Card]:
        """Get the exposed card for a player.

        Args:
            seat: Player's seat number

        Returns:
            The Card object if exposed, None otherwise
        """
        if seat not in self.state.players:
            return None

        player = self.state.players[seat]
        if player.exposed_card_index is None or not player.hole_cards:
            return None

        if player.exposed_card_index < len(player.hole_cards):
            return player.hole_cards[player.exposed_card_index]

        return None
