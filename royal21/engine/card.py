"""Card representation for the game."""

from dataclasses import dataclass


@dataclass
class Card:
    """Represents a single playing card."""

    SUITS = ['♠', '♥', '♦', '♣']
    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    RANK_VALUES = {
        '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
        'J': 10, 'Q': 10, 'K': 10, 'A': 11
    }

    rank: str  # '2', '3', ..., 'K', 'A'
    suit: str  # '♠', '♥', '♦', '♣'

    @property
    def value(self) -> int:
        """Return numeric value using blackjack rules (2-10=face, J/Q/K=10, A=11)."""
        return self.RANK_VALUES[self.rank]

    @property
    def display(self) -> str:
        """Return display string like 'K♠'."""
        return f"{self.rank}{self.suit}"

    def __str__(self) -> str:
        return self.display

    def __repr__(self) -> str:
        return f"Card({self.rank}{self.suit})"
