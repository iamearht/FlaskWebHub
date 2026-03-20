"""Seating management for tables."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Seat:
    """Represents a seat at the table."""
    seat_number: int  # 0 to 6 (7 max seats)
    player_name: Optional[str] = None
    player_id: Optional[str] = None
    stack: int = 0  # Chip count
    is_active: bool = False  # Currently in game
    is_sitting_out: bool = False  # Physically present but not playing


class SeatingManager:
    """Manages seat assignments and player positions."""

    def __init__(self, max_seats: int = 7):
        """Initialize seating for a table."""
        self.max_seats = max_seats
        self.seats: dict[int, Seat] = {
            i: Seat(seat_number=i) for i in range(max_seats)
        }
        self.button_seat: Optional[int] = None

    def assign_player(
        self, seat_num: int, player_name: str, player_id: str, stack: int
    ) -> bool:
        """
        Assign a player to a seat.

        Args:
            seat_num: Seat number (0-6).
            player_name: Player's name.
            player_id: Unique player ID.
            stack: Initial chip stack.

        Returns:
            True if assignment successful, False if seat is taken or invalid.
        """
        if seat_num < 0 or seat_num >= self.max_seats:
            return False

        seat = self.seats[seat_num]
        if seat.player_id is not None:
            return False  # Seat taken

        seat.player_name = player_name
        seat.player_id = player_id
        seat.stack = stack
        seat.is_active = True
        seat.is_sitting_out = False

        return True

    def remove_player(self, seat_num: int) -> bool:
        """
        Remove a player from a seat.

        Args:
            seat_num: Seat number (0-6).

        Returns:
            True if removed, False if seat was empty.
        """
        if seat_num < 0 or seat_num >= self.max_seats:
            return False

        seat = self.seats[seat_num]
        if seat.player_id is None:
            return False  # Seat already empty

        seat.player_name = None
        seat.player_id = None
        seat.stack = 0
        seat.is_active = False
        seat.is_sitting_out = False

        return True

    def get_active_seats(self) -> list[int]:
        """Get list of seat numbers with active players."""
        return [
            i for i in range(self.max_seats)
            if self.seats[i].player_id is not None and self.seats[i].is_active
        ]

    def get_occupied_seats(self) -> list[int]:
        """Get list of all occupied seats (active and sitting out)."""
        return [
            i for i in range(self.max_seats)
            if self.seats[i].player_id is not None
        ]

    def get_seat(self, seat_num: int) -> Optional[Seat]:
        """Get seat by number."""
        if 0 <= seat_num < self.max_seats:
            return self.seats[seat_num]
        return None

    def set_button(self, seat_num: int) -> bool:
        """Set the button position."""
        if seat_num < 0 or seat_num >= self.max_seats:
            return False
        self.button_seat = seat_num
        return True

    def get_button(self) -> Optional[int]:
        """Get current button seat."""
        return self.button_seat

    def rotate_button(self) -> Optional[int]:
        """
        Rotate button to next active seat clockwise.

        Returns:
            New button seat number, or None if no active seats.
        """
        active = self.get_active_seats()
        if not active:
            return None

        if self.button_seat is None:
            # First button: seat 0 or first active seat
            self.button_seat = active[0]
        else:
            # Find next active seat after button
            current_index = (
                active.index(self.button_seat)
                if self.button_seat in active
                else -1
            )
            next_index = (current_index + 1) % len(active)
            self.button_seat = active[next_index]

        return self.button_seat

    def player_count(self) -> int:
        """Get number of active players."""
        return len(self.get_active_seats())

    def is_full(self) -> bool:
        """Check if table is full."""
        return self.player_count() >= self.max_seats
