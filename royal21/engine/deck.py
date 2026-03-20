"""Deck management for the game."""

import random
from typing import List
from .card import Card


class Deck:
    """Manages a standard 52-card deck."""

    def __init__(self):
        """Initialize a full shuffled deck."""
        self.cards: List[Card] = []
        self._create_deck()

    def _create_deck(self):
        """Create a fresh 52-card deck."""
        self.cards = [
            Card(rank, suit)
            for suit in Card.SUITS
            for rank in Card.RANKS
        ]
        self.shuffle()

    def shuffle(self):
        """Shuffle the deck."""
        random.shuffle(self.cards)

    def draw(self) -> Card:
        """Draw and return the top card."""
        if not self.cards:
            raise ValueError("Cannot draw from empty deck")
        return self.cards.pop()

    def put_back(self, cards: List[Card]):
        """Put cards back into the deck (without shuffling)."""
        self.cards.extend(cards)

    def reshuffle_with(self, cards: List[Card]):
        """Put cards back and reshuffle."""
        self.put_back(cards)
        self.shuffle()

    @property
    def remaining(self) -> int:
        """Return number of cards remaining in deck."""
        return len(self.cards)

    def is_empty(self) -> bool:
        """Check if deck is empty."""
        return len(self.cards) == 0
