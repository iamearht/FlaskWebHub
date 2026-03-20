import random
from typing import List
from .card import Card, Rank, Suit


class Deck:
    """Represents a standard 52-card deck."""

    def __init__(self, shuffle: bool = True):
        """
        Initialize a standard 52-card deck.

        Args:
            shuffle: If True, shuffle the deck immediately after creation.
        """
        self.cards: List[Card] = []
        self._create_deck()
        if shuffle:
            self.shuffle()

    def _create_deck(self) -> None:
        """Create a standard 52-card deck (no shuffling)."""
        self.cards = [
            Card(rank, suit)
            for suit in Suit
            for rank in Rank
        ]

    def shuffle(self) -> None:
        """Shuffle the deck in-place."""
        random.shuffle(self.cards)

    def deal(self, num_cards: int = 1) -> List[Card]:
        """
        Deal cards from the deck.

        Args:
            num_cards: Number of cards to deal.

        Returns:
            List of cards dealt. If not enough cards remain, returns
            fewer cards (or empty list if deck is empty).
        """
        if num_cards <= 0:
            return []
        dealt = self.cards[:num_cards]
        self.cards = self.cards[num_cards:]
        return dealt

    def draw_one(self) -> Card | None:
        """
        Draw a single card from the deck.

        Returns:
            A Card, or None if deck is empty.
        """
        if self.cards:
            return self.deal(1)[0]
        return None

    def remaining(self) -> int:
        """Return number of cards remaining in deck."""
        return len(self.cards)

    def is_empty(self) -> bool:
        """Check if deck is empty."""
        return len(self.cards) == 0

    def __len__(self) -> int:
        return len(self.cards)

    def __repr__(self) -> str:
        return f"Deck({len(self.cards)} cards)"
