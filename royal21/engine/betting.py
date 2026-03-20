"""Betting calculation utilities for pot limit poker."""

from typing import Optional
from .game_state import GameState


class BettingCalculator:
    """Helper class for betting calculations and validation."""

    @staticmethod
    def get_call_amount(state: GameState, seat: int) -> int:
        """Calculate how much a player needs to call.

        Args:
            state: Current game state
            seat: Player's seat number

        Returns:
            Amount needed to call (0 if can check)
        """
        if seat not in state.players:
            return 0
        return state.current_high_bet - state.players[seat].current_bet

    @staticmethod
    def get_min_raise(last_raise_size: int, current_high_bet: int) -> int:
        """Calculate minimum raise amount (pot limit).

        In pot limit, the minimum raise is equal to the size of the last raise.

        Args:
            last_raise_size: Size of the previous raise
            current_high_bet: Current high bet amount

        Returns:
            Minimum total bet amount
        """
        # Min raise = current high bet + last raise size
        return current_high_bet + last_raise_size

    @staticmethod
    def get_max_raise(state: GameState, seat: int, last_raise_size: int) -> int:
        """Calculate maximum raise amount (pot limit formula).

        Pot limit formula: max_total = P + (3 × B)
        where:
          P = total pot in play (main_pot + all pending current_bets)
          B = opponent's last bet (current_high_bet)

        This is the TOTAL amount they bet this action (call + raise combined).

        Args:
            state: Current game state
            seat: Player's seat number
            last_raise_size: Size of last raise (for calculating min)

        Returns:
            Maximum total bet amount
        """
        if seat not in state.players:
            return 0

        # Calculate P = total pot in play (main_pot + all pending bets)
        pot_with_pending = state.pot.main_pot + sum(
            p.current_bet for p in state.players.values() if p.current_bet > 0
        )

        # B = opponent's last bet (current_high_bet)
        opponent_bet = state.current_high_bet

        # If no previous bets in round (first action), max = pot only
        if opponent_bet == 0:
            max_total = pot_with_pending
        else:
            # Formula: P + 3B (with 3× multiplier for subsequent bets)
            max_total = pot_with_pending + (3 * opponent_bet)

        # Cap by player's total available chips (current_bet already committed + remaining stack)
        # A raise to (current_bet + stack) costs exactly stack chips, which is always affordable
        player = state.players[seat]
        player_total = player.current_bet + player.stack
        return min(max_total, player_total)

    @staticmethod
    def get_max_bet_no_raise(state: GameState) -> int:
        """Calculate max bet when no one has bet yet (first to act).

        When first to act with no bet, max bet = pot size.

        Args:
            state: Current game state

        Returns:
            Maximum bet amount
        """
        if state.current_actor is None or state.current_actor not in state.players:
            return 0

        pot = state.pot.main_pot + sum(
            p.current_bet for p in state.players.values() if p.current_bet > 0
        )
        player_stack = state.players[state.current_actor].stack
        return min(pot, player_stack)

    @staticmethod
    def get_next_active_seat(state: GameState, after_seat: int) -> Optional[int]:
        """Find next seated, non-folded player (wraps at 6→0).

        Args:
            state: Current game state
            after_seat: Start searching after this seat

        Returns:
            Next active player's seat, or None if no one left
        """
        for offset in range(1, 7):
            check_seat = (after_seat + offset) % 7
            if check_seat in state.players:
                player = state.players[check_seat]
                if player and not player.is_folded and player.is_active:
                    return check_seat
        return None

    @staticmethod
    def is_betting_round_complete(state: GameState) -> bool:
        """Check if all active players have equal bets AND have all acted on current bet level.

        Betting round is complete only when:
        1. All active players have equal bets
        2. All active players have acted on the current bet level (except all-in players)

        Fold-out (only 1 player left) is handled separately in the game loop.

        Args:
            state: Current game state

        Returns:
            True if betting round is complete, False otherwise
        """
        active_players = [
            p for p in state.players.values()
            if p and not p.is_folded and p.is_active
        ]

        # If only 1 or fewer active players, don't consider betting complete here
        # The game loop handles the fold-out case separately
        if len(active_players) <= 1:
            return False

        # Check if all active players have equal current_bet amounts
        bets = [p.current_bet for p in active_players]
        if len(set(bets)) != 1:
            return False  # Bets are not equal, round not complete

        # Check if all active (non-all-in) players have acted on the current bet
        # (All-in players are exempt from this check since they can't act further)
        for player in active_players:
            if not player.is_all_in and not player.has_acted_on_current_bet:
                return False  # At least one player hasn't acted yet

        return True  # All conditions met

    @staticmethod
    def is_bet_valid(
        state: GameState,
        seat: int,
        action_type: str,
        amount: Optional[int],
        last_raise_size: int
    ) -> tuple[bool, str]:
        """Validate a betting action.

        Args:
            state: Current game state
            seat: Player's seat
            action_type: "call", "raise", "check", "fold"
            amount: Bet amount (for raise/call)
            last_raise_size: Size of last raise

        Returns:
            (is_valid, error_message)
        """
        if seat not in state.players:
            return False, "Invalid seat"

        player = state.players[seat]
        call_amount = BettingCalculator.get_call_amount(state, seat)

        if action_type == "fold":
            return True, ""

        elif action_type == "check":
            if call_amount == 0:
                return True, ""
            else:
                return False, "Cannot check - must call, raise, or fold"

        elif action_type == "call":
            if player.stack < call_amount:
                return False, f"Not enough chips to call. Need {call_amount}, have {player.stack}"
            return True, ""

        elif action_type == "raise":
            if amount is None:
                return False, "Raise amount required"

            min_raise = BettingCalculator.get_min_raise(last_raise_size, state.current_high_bet)
            max_raise = BettingCalculator.get_max_raise(state, seat, last_raise_size)

            if amount < min_raise:
                return False, f"Minimum raise is {min_raise}, you bet {amount}"
            if amount > max_raise:
                return False, f"Maximum bet is {max_raise}, you bet {amount}"
            if player.stack < (amount - player.current_bet):
                return False, f"Not enough chips. Need {amount - player.current_bet}, have {player.stack}"

            return True, ""

        else:
            return False, f"Unknown action: {action_type}"
