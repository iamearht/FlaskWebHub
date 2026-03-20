"""Pot calculation and distribution."""

from typing import List, Tuple
from .game_state import GameState, PlayerState


class PotManager:
    """Manages pot calculations and chip distribution."""

    @staticmethod
    def calculate_pot(game_state: GameState) -> int:
        """Calculate total pot size."""
        return game_state.pot.main_pot

    @staticmethod
    def get_player_contribution(game_state: GameState, seat: int) -> int:
        """Get total bet amount from a player."""
        return game_state.pot.get_player_contribution(seat)

    @staticmethod
    def distribute_pot_to_winners(
        game_state: GameState, winners: List[int]
    ) -> dict[int, int]:
        """
        Distribute pot equally among winners.

        Args:
            game_state: Current game state.
            winners: List of winning player seats.

        Returns:
            Dict mapping seat number to chips won.
        """
        if not winners:
            return {}

        total_pot = game_state.pot.main_pot
        chips_per_winner = total_pot // len(winners)
        remainder = total_pot % len(winners)

        distribution = {}
        for i, seat in enumerate(winners):
            amount = chips_per_winner + (1 if i < remainder else 0)
            distribution[seat] = amount

        return distribution

    @staticmethod
    def add_chips_to_player(game_state: GameState, seat: int, amount: int) -> None:
        """Add chips to player's stack."""
        player = game_state.get_player(seat)
        if player:
            player.stack += amount

    @staticmethod
    def subtract_chips_from_player(game_state: GameState, seat: int, amount: int) -> bool:
        """
        Remove chips from player's stack.

        Args:
            game_state: Current game state.
            seat: Player seat.
            amount: Chips to remove.

        Returns:
            True if successful, False if insufficient chips.
        """
        player = game_state.get_player(seat)
        if not player or player.stack < amount:
            return False

        player.stack -= amount
        return True

    @staticmethod
    def is_pot_limit_bet_valid(
        game_state: GameState,
        seat: int,
        raise_amount: int,
    ) -> bool:
        """
        Check if a pot-limit bet is valid.

        Pot-limit: max raise = current pot + call amount

        Args:
            game_state: Current game state.
            seat: Player seat.
            raise_amount: Amount player wants to raise to.

        Returns:
            True if valid, False otherwise.
        """
        player = game_state.get_player(seat)
        if not player:
            return False

        # Max they can raise to: pot + their current bet + call amount
        current_pot = game_state.pot.main_pot
        call_amount = game_state.current_high_bet - player.bet_this_round
        max_raise = current_pot + call_amount + player.bet_this_round

        return raise_amount <= max_raise and raise_amount <= player.stack

    @staticmethod
    def get_max_bet(game_state: GameState, seat: int) -> int:
        """
        Get maximum amount a player can bet (pot-limit).

        Returns:
            Maximum bet amount for this player.
        """
        player = game_state.get_player(seat)
        if not player:
            return 0

        current_pot = game_state.pot.main_pot
        call_amount = max(0, game_state.current_high_bet - player.bet_this_round)
        max_bet = current_pot + call_amount + player.bet_this_round

        return min(max_bet, player.stack)

    @staticmethod
    def get_call_amount(game_state: GameState, seat: int) -> int:
        """
        Get amount player needs to call.

        Returns:
            Chips needed to call, or 0 if no bet to call.
        """
        player = game_state.get_player(seat)
        if not player:
            return 0

        return max(0, game_state.current_high_bet - player.bet_this_round)

    @staticmethod
    def is_hand_over(game_state: GameState) -> bool:
        """
        Check if hand is decided (only one player left or showdown reached).

        Returns:
            True if hand should end.
        """
        active = game_state.get_active_players()
        return len(active) <= 1
