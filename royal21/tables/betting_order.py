"""Betting order and action sequence management."""

from typing import Optional
from .seating import SeatingManager


class BettingOrder:
    """Manages action order and betting positions."""

    def __init__(self, seating: SeatingManager):
        """Initialize betting order."""
        self.seating = seating

    def get_big_blind_seat(self) -> Optional[int]:
        """
        Get the big blind seat (button position).

        In this game:
        - Button = Big Blind position
        - Big blind posts 2 antes

        Returns:
            Seat number of big blind, or None if no button set.
        """
        return self.seating.get_button()

    def get_small_blind_seat(self) -> Optional[int]:
        """
        Get the seat immediately left of button (small blind position).

        In this game, small blind position is where action starts.

        Returns:
            Seat number of small blind, or None if no button set.
        """
        button = self.seating.get_button()
        if button is None:
            return None

        active = self.seating.get_active_seats()
        if not active:
            return None

        # Find next seat clockwise from button
        button_index = active.index(button) if button in active else -1
        if button_index == -1:
            return None

        next_index = (button_index + 1) % len(active)
        return active[next_index]

    def get_action_order(self) -> list[int]:
        """
        Get action order starting from small blind (left of button).

        Returns:
            List of seat numbers in action order (clockwise from small blind).
        """
        active = self.seating.get_active_seats()
        if not active:
            return []

        button = self.seating.get_button()
        if button is None:
            # No button set yet; start from seat 0
            return active

        # Find button index and rotate to start from next seat
        button_index = active.index(button) if button in active else -1
        if button_index == -1:
            return active

        # Rotate so small blind (next after button) is first
        start_index = (button_index + 1) % len(active)
        return active[start_index:] + active[:start_index]

    def get_next_to_act(self, current_actor: Optional[int]) -> Optional[int]:
        """
        Get next player to act in betting round.

        Args:
            current_actor: Seat number of current actor, or None for first.

        Returns:
            Seat number of next actor, or None if only one player left.
        """
        action_order = self.get_action_order()
        active = self.seating.get_active_seats()

        if not active:
            return None

        if current_actor is None:
            # First action: small blind
            return action_order[0] if action_order else None

        if current_actor not in action_order:
            return None

        current_index = action_order.index(current_actor)
        next_index = (current_index + 1) % len(action_order)
        return action_order[next_index]

    def is_last_to_act(self, seat_num: int) -> bool:
        """Check if a seat is last to act in action order."""
        action_order = self.get_action_order()
        return action_order and action_order[-1] == seat_num if action_order else False

    def before_button(self, seat_a: int, seat_b: int) -> bool:
        """
        Check if seat_a comes before seat_b in action order.

        Returns:
            True if seat_a acts before seat_b.
        """
        action_order = self.get_action_order()
        if not action_order or seat_a not in action_order or seat_b not in action_order:
            return False

        idx_a = action_order.index(seat_a)
        idx_b = action_order.index(seat_b)
        return idx_a < idx_b
