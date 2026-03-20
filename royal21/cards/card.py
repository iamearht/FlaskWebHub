from dataclasses import dataclass
from enum import Enum


class Suit(str, Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"


class Rank(str, Enum):
    ACE = "A"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"


@dataclass(frozen=True)
class Card:
    """Represents a single playing card."""
    rank: Rank
    suit: Suit

    def value(self, allow_ace_as_one: bool = False) -> int:
        """
        Returns the blackjack value of the card.

        Args:
            allow_ace_as_one: If True, Ace counts as 1 instead of 11.
                             Should be set based on hand context.

        Returns:
            Card value (1-11 for regular cards, 11 or 1 for Ace)
        """
        if self.rank == Rank.ACE:
            return 1 if allow_ace_as_one else 11
        elif self.rank in (Rank.JACK, Rank.QUEEN, Rank.KING):
            return 10
        else:
            return int(self.rank.value)

    def display(self) -> str:
        """Returns formatted card display (e.g., 'A♠', '10♥', 'K♦')"""
        return f"{self.rank.value}{self.suit.value}"

    def __str__(self) -> str:
        return self.display()

    def __repr__(self) -> str:
        return f"Card({self.rank.value}{self.suit.value})"
