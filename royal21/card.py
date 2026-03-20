"""
Card and Deck classes for Royal 21 game.
"""
import random
from enum import Enum
from typing import List, Tuple


class Suit(Enum):
    """Card suits."""
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"
    SPADES = "♠"


class Rank(Enum):
    """Card ranks."""
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


class Card:
    """Represents a playing card."""

    def __init__(self, rank: Rank, suit: Suit):
        self.rank = rank
        self.suit = suit

    def __repr__(self) -> str:
        return f"{self.rank.value}{self.suit.value}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit

    def value(self) -> int:
        """Blackjack value: 2-10 face value, JQK=10, A=1 (handled in hand total)."""
        if self.rank == Rank.ACE:
            return 1  # Aces handled in soft-hand logic
        if self.rank in (Rank.JACK, Rank.QUEEN, Rank.KING):
            return 10
        return int(self.rank.value)

    def is_ten_value(self) -> bool:
        """Is this card a 10-value card (10, J, Q, K)?"""
        return self.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING)

    def is_ace(self) -> bool:
        """Is this card an Ace?"""
        return self.rank == Rank.ACE

    def rank_order(self) -> int:
        """Rank order for blackjack comparison (higher is better). For 10-value cards only."""
        if self.rank == Rank.KING:
            return 4  # K > Q > J > 10
        if self.rank == Rank.QUEEN:
            return 3
        if self.rank == Rank.JACK:
            return 2
        if self.rank == Rank.TEN:
            return 1
        return 0


class Deck:
    """Standard 52-card deck with seedable shuffle."""

    def __init__(self, seed: int = None):
        """Initialize deck with optional seed for reproducible shuffles."""
        self.seed = seed
        self.cards: List[Card] = []
        self._initialize_deck()

    def _initialize_deck(self):
        """Create a full 52-card deck."""
        self.cards = []
        for suit in Suit:
            for rank in Rank:
                self.cards.append(Card(rank, suit))

    def shuffle(self):
        """Shuffle deck in place. Use seed if provided."""
        if self.seed is not None:
            random.seed(self.seed)
        random.shuffle(self.cards)

    def deal(self) -> Card:
        """Deal one card from top of deck."""
        if not self.cards:
            raise RuntimeError("Deck is empty")
        return self.cards.pop(0)

    def cards_remaining(self) -> int:
        """Number of cards left in deck."""
        return len(self.cards)

    def reset(self):
        """Reset deck to full 52 cards and reshuffle."""
        self._initialize_deck()
        self.shuffle()
