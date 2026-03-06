"""
Main Royal 21 game engine - orchestrates game flow and validates actions.
"""
from typing import List, Optional, Tuple, Dict
from card import Card, Deck
from hand import Hand, evaluate_hand, rank_hands, compare_natural_blackjacks_special
from game_state import GameState, PlayerState, Phase, ActionType


class GameEngine:
    """Main game engine for Royal 21."""

    def __init__(self, game_id: str, num_players: int, starting_stack: int, seed: int = None):
        self.game = GameState(
            game_id=game_id,
            num_players=num_players,
            small_blind=1,  # Antes/posts
            big_blind=1,
            deck=Deck(seed=seed) if seed else Deck()
        )
        self.starting_stack = starting_stack

        # Initialize players
        for seat in range(num_players):
            self.game.players.append(
                PlayerState(
                    seat_index=seat,
                    username=f"Player {seat + 1}",
                    stack=starting_stack,
                )
            )

    def start_hand(self):
        """Start a new hand: SETUP phase."""
        # Reset previous hand state (only if transitioning from HAND_OVER)
        if self.game.phase == Phase.HAND_OVER:
            self.game.reset_hand()

        self.game.phase = Phase.SETUP

        # Post antes/blinds
        for player in self.game.players:
            if not player.in_hand:
                continue

            # Escrow ante: 1 chip
            if player.chips_remaining() >= 1:
                player.escrow_circle += 1
                player.stack -= 1
                self.game.escrow_pot += 1
            else:
                player.all_in = True

        # Button posts: 1 chip to normal
        button_player = self.game.players[self.game.button_index]
        if button_player.chips_remaining() >= 1:
            button_player.normal_circle += 1
            button_player.stack -= 1
            self.game.normal_pot += 1
        else:
            button_player.all_in = True

        # Shuffle and deal
        self.game.deck.reset()
        for player in self.game.players:
            if player.in_hand:
                player.hole_cards = [self.game.deck.deal(), self.game.deck.deal()]
                player.original_hand = Hand(player.hole_cards, "original")

        # Set action order (left of button)
        active_seats = self.game.active_seats()
        button_pos = active_seats.index(self.game.button_index) if self.game.button_index in active_seats else 0
        self.game.current_action_index = active_seats[(button_pos + 1) % len(active_seats)]

        self.game.phase = Phase.PREFLOP
        self.game.log_action("Hand started. Preflop betting begins.")

    def get_legal_actions(self, player_seat: int) -> Dict[str, any]:
        """
        Get legal actions for a player in current phase.

        Returns dict with:
        {
            "escrow_add": bool,
            "escrow_options": List[int],
            "actions": List[ActionType],
            "fold": bool,
            "call_amount": int (if call is legal),
            "max_raise_to": int (if raise is legal),
            "min_raise_to": int,
            "hit": bool,
            "stand": bool,
            "double": bool,
            "split": bool,
        }
        """
        player = self.game.get_player(player_seat)
        if not player or player.folded or not player.in_hand:
            return {"error": "Player not in hand"}

        if self.game.current_action_index != player_seat:
            return {"error": "Not player's turn"}

        result = {
            "escrow_add": False,
            "escrow_options": [],
            "actions": [],
            "fold": False,
            "call_amount": 0,
            "max_raise_to": 0,
            "min_raise_to": 0,
            "hit": False,
            "stand": False,
            "double": False,
            "split": False,
        }

        if self.game.phase == Phase.PREFLOP or self.game.phase == Phase.RIVER:
            # Betting phase: escrow step then normal step

            # Check if this is first action (reveal rule)
            is_first_action = action_count_for_player(self.game, player_seat) == 0

            # Escrow step: can add escrow unless escrow-locked
            if not player.hit_taken:
                result["escrow_add"] = True
                # Options: 0 to chips_remaining
                result["escrow_options"] = list(range(0, player.chips_remaining() + 1))

            # Normal betting step
            to_call = max(0, self.game.current_highest_normal - player.normal_circle)
            result["fold"] = True

            if to_call == 0:
                # No bet to call - can check or bet
                result["actions"] = ["check", "bet"]
                result["max_raise_to"] = self.game.table_total()
                result["min_raise_to"] = 1 if self.game.table_total() > 0 else 0
            else:
                # Facing a bet - can fold, call, or raise
                result["actions"] = ["call", "raise"]
                result["call_amount"] = to_call
                result["max_raise_to"] = self.game.current_highest_normal + self.game.table_total()
                result["min_raise_to"] = self.game.current_highest_normal + 1

            # First action: must reveal a card
            if is_first_action and len(player.hole_cards) == 2:
                result["must_reveal"] = True
                result["reveal_options"] = list(range(2))  # Index 0 or 1

        elif self.game.phase == Phase.DRAW:
            # Draw phase: HIT / STAND / DOUBLE / SPLIT
            result["stand"] = True

            # Check if player has active hands
            hands = list(player.split_hands.values()) if player.split_hands else [player.original_hand]
            if hands and len(hands) > 0:
                # Can hit or double (if not already doubled and within constraints)
                current_hand = hands[-1]  # Last hand being played

                result["hit"] = not current_hand.busted and not current_hand.stood
                result["double"] = (
                    not current_hand.busted
                    and not current_hand.doubled
                    and len(current_hand.drawn_cards) == 0  # Only before any hits
                    and player.chips_remaining() >= (player.normal_circle / 2)
                )

                # Split: only if 2 hole cards, same rank, and not already split
                if (
                    len(player.hole_cards) == 2
                    and player.hole_cards[0].rank == player.hole_cards[1].rank
                    and not player.split_hands
                    and len(current_hand.drawn_cards) == 0
                ):
                    result["split"] = True

        return result

    def take_action(self, player_seat: int, action: ActionType, **kwargs) -> Tuple[bool, str]:
        """
        Execute an action for a player.

        Returns (success, message)
        """
        player = self.game.get_player(player_seat)
        if not player or player.folded or not player.in_hand:
            return False, "Player not in hand"

        if self.game.current_action_index != player_seat:
            return False, "Not player's turn"

        # --- PREFLOP / RIVER BETTING ---
        if self.game.phase in (Phase.PREFLOP, Phase.RIVER):
            if action == ActionType.ESCROW_ADD:
                amount = kwargs.get("amount", 0)
                if player.hit_taken and self.game.phase == Phase.RIVER:
                    return False, "Cannot add escrow after hitting in draw phase"
                if not player.can_bet(amount):
                    return False, "Not enough chips"
                player.escrow_circle += amount
                player.stack -= amount
                self.game.escrow_pot += amount
                self.game.log_action(f"Player {player.username} adds {amount} escrow")
                return True, "Escrow added"

            # Check reveal rule on first action
            is_first_action = action_count_for_player(self.game, player_seat) == 0
            if is_first_action and "reveal_index" in kwargs:
                idx = kwargs["reveal_index"]
                if idx not in (0, 1):
                    return False, "Invalid reveal index"
                player.revealed_card = player.hole_cards[idx]

            if action == ActionType.FOLD:
                player.folded = True
                self.game.log_action(f"Player {player.username} folds")
                return True, "Folded"

            if action == ActionType.CHECK:
                if self.game.current_highest_normal > player.normal_circle:
                    return False, "Cannot check facing a bet"
                self.game.log_action(f"Player {player.username} checks")
                # Move to next player
                self._advance_action()
                return True, "Checked"

            if action == ActionType.CALL:
                to_call = max(0, self.game.current_highest_normal - player.normal_circle)
                if not player.can_bet(to_call):
                    # Go all-in
                    to_call = player.chips_remaining()
                    player.all_in = True
                player.normal_circle += to_call
                player.stack -= to_call
                self.game.normal_pot += to_call
                self.game.log_action(f"Player {player.username} calls {to_call}")
                self._advance_action()
                return True, "Called"

            if action == ActionType.BET:
                amount = kwargs.get("amount", 0)
                if self.game.current_highest_normal > player.normal_circle:
                    return False, "Cannot bet facing a higher bet (must call/raise)"
                if amount < 1 or amount > self.game.table_total():
                    return False, f"Invalid bet amount (1 to {self.game.table_total()})"
                if not player.can_bet(amount):
                    return False, "Not enough chips"
                to_add = amount - player.normal_circle
                player.normal_circle += to_add
                player.stack -= to_add
                self.game.normal_pot += to_add
                self.game.current_highest_normal = amount
                self.game.current_highest_bet_from = player_seat
                self.game.log_action(f"Player {player.username} bets {amount}")
                self._advance_action()
                return True, "Bet placed"

            if action == ActionType.RAISE:
                raise_to = kwargs.get("raise_to", 0)
                max_raise = self.game.current_highest_normal + self.game.table_total()
                if raise_to < self.game.current_highest_normal or raise_to > max_raise:
                    return False, f"Invalid raise (must be between {self.game.current_highest_normal} and {max_raise})"
                to_add = raise_to - player.normal_circle
                if not player.can_bet(to_add):
                    return False, "Not enough chips"
                player.normal_circle += to_add
                player.stack -= to_add
                self.game.normal_pot += to_add
                self.game.current_highest_normal = raise_to
                self.game.current_highest_bet_from = player_seat
                self.game.log_action(f"Player {player.username} raises to {raise_to}")
                self._advance_action()
                return True, "Raised"

        # --- DRAW PHASE ---
        elif self.game.phase == Phase.DRAW:
            hands = list(player.split_hands.values()) if player.split_hands else [player.original_hand]
            current_hand = hands[-1] if hands else player.original_hand

            if action == ActionType.STAND:
                current_hand.stood = True
                self.game.log_action(f"Player {player.username} stands ({len(current_hand.all_cards())} cards)")
                self._advance_draw()
                return True, "Stood"

            if action == ActionType.HIT:
                card = self.game.deck.deal()
                current_hand.add_drawn_card(card)
                player.hit_taken = True
                self.game.log_action(f"Player {player.username} hits (total now {current_hand.total()})")
                if current_hand.busted:
                    current_hand.stood = True  # Auto-stand if busted
                    self._advance_draw()
                return True, "Hit"

            if action == ActionType.DOUBLE:
                if len(current_hand.drawn_cards) > 0:
                    return False, "Can only double before drawing"
                if not player.can_bet(player.normal_circle):  # Need to match original bet
                    return False, "Not enough chips to double"
                player.normal_circle *= 2
                player.stack -= player.normal_circle // 2
                current_hand.doubled = True
                card = self.game.deck.deal()
                current_hand.add_drawn_card(card)
                current_hand.stood = True
                player.hit_taken = False  # Double doesn't count as "hit" for escrow lock
                self.game.log_action(f"Player {player.username} doubles down (total {current_hand.total()})")
                self._advance_draw()
                return True, "Doubled"

            if action == ActionType.SPLIT:
                if player.hole_cards[0].rank != player.hole_cards[1].rank:
                    return False, "Cannot split unequal cards"
                if not player.can_bet(player.normal_circle // 2):
                    return False, "Not enough chips to split"

                # Create split hands
                split_a = Hand([player.hole_cards[0]], "split_a")
                split_b = Hand([player.hole_cards[1]], "split_b")

                # Deal one card to each
                split_a.add_drawn_card(self.game.deck.deal())
                split_b.add_drawn_card(self.game.deck.deal())

                player.split_hands = {"split_a": split_a, "split_b": split_b}
                # Duplicate the normal circle for the split
                player.normal_circle *= 2
                player.stack -= player.normal_circle // 2

                self.game.log_action(f"Player {player.username} splits")
                # Start playing split hands
                self._advance_draw()
                return True, "Split"

        return False, "Invalid action for current phase"

    def _advance_action(self):
        """Move to next player's turn in betting phase."""
        active = self.game.active_seats()
        if len(active) <= 1:
            self._end_betting_phase()
            return

        # Check if all active players have matched the current highest bet
        all_matched = all(
            self.game.get_player(seat).normal_circle >= self.game.current_highest_normal
            for seat in active
            if not self.game.get_player(seat).all_in
        )

        if all_matched:
            self._end_betting_phase()
        else:
            # Move to next player
            current_seat = self.game.current_action_index
            pos = active.index(current_seat)
            self.game.current_action_index = active[(pos + 1) % len(active)]
            self.game.action_count += 1

    def _end_betting_phase(self):
        """End current betting phase and transition to next."""
        if self.game.phase == Phase.PREFLOP:
            active = self.game.active_seats()
            if len(active) <= 1:
                self._resolve_showdown()
            else:
                self.game.phase = Phase.DRAW
                self.game.current_action_index = active[0]
        elif self.game.phase == Phase.DRAW:
            # All draws done, move to river
            self.game.phase = Phase.RIVER

            # Post antes for river phase
            for player in self.game.players:
                if not player.in_hand or player.folded:
                    continue

                # Escrow ante: 1 chip
                if player.chips_remaining() >= 1:
                    player.escrow_circle += 1
                    player.stack -= 1
                    self.game.escrow_pot += 1
                else:
                    player.all_in = True

            # Button posts: 1 chip to normal
            button_player = self.game.players[self.game.button_index]
            if button_player.in_hand and not button_player.folded:
                if button_player.chips_remaining() >= 1:
                    button_player.normal_circle += 1
                    button_player.stack -= 1
                    self.game.normal_pot += 1
                else:
                    button_player.all_in = True

            active = self.game.active_seats()
            if active:
                self.game.current_action_index = active[0]
                self.game.current_highest_normal = 0
        elif self.game.phase == Phase.RIVER:
            self._resolve_showdown()

    def _advance_draw(self):
        """Advance in draw phase (next player or to river)."""
        # This is simplified; in full impl, would handle each split hand properly
        active = self.game.active_seats()
        if len(active) <= 1:
            self._end_betting_phase()
            return

        current_pos = active.index(self.game.current_action_index)
        next_pos = (current_pos + 1) % len(active)
        if next_pos <= current_pos:
            # Everyone has drawn
            self._end_betting_phase()
        else:
            self.game.current_action_index = active[next_pos]

    def _resolve_showdown(self):
        """Resolve showdown and distribute pots."""
        self.game.phase = Phase.SHOWDOWN
        # TODO: Implement complete showdown logic with split-hand halves and escrow layering
        self.game.phase = Phase.HAND_OVER
        self.game.log_action("Hand complete.")

    def state_for_player(self, player_seat: int) -> Dict:
        """Get game state visible to a player."""
        return {
            "game_id": self.game.game_id,
            "phase": self.game.phase.value,
            "players": [
                {
                    "seat": p.seat_index,
                    "username": p.username,
                    "stack": p.stack,
                    "normal_circle": p.normal_circle,
                    "escrow_circle": p.escrow_circle,
                    "in_hand": p.in_hand and not p.folded,
                    "revealed_card": str(p.revealed_card) if p.revealed_card else None,
                    "card_count": len(p.hole_cards) + sum(len(h.drawn_cards) for h in p.split_hands.values()) if p.split_hands else len(p.hole_cards),
                }
                for p in self.game.players
            ],
            "current_action": self.game.current_action_index,
            "table_total": self.game.table_total(),
            "normal_pot": self.game.normal_pot,
            "escrow_pot": self.game.escrow_pot,
            "logs": self.game.logs[-10:],  # Last 10 log entries
        }


def action_count_for_player(game: GameState, seat: int) -> int:
    """Count how many (escrow + normal) actions a player has taken this round."""
    # Simplified - in full impl would track per-player
    return 0
