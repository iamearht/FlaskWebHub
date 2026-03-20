from typing import List
from .card import Card, Rank


class Hand:
    """Represents a player's hand of cards."""

    def __init__(self, cards: List[Card] | None = None):
        """
        Initialize a hand with cards.

        Args:
            cards: List of Card objects. Empty list if None.
        """
        self.cards = cards if cards is not None else []

    def add_card(self, card: Card) -> None:
        """Add a card to the hand."""
        self.cards.append(card)

    def add_cards(self, cards: List[Card]) -> None:
        """Add multiple cards to the hand."""
        self.cards.extend(cards)

    def total(self) -> int:
        """
        Calculate the blackjack-style total.
        Aces are valued at 11 unless that would cause a bust,
        in which case they're valued at 1.

        Returns:
            Total hand value (can exceed 21, indicating a bust).
        """
        if not self.cards:
            return 0

        # Count aces and sum other cards at face value (Ace=11)
        total = 0
        aces = 0

        for card in self.cards:
            if card.rank == Rank.ACE:
                aces += 1
                total += 11
            else:
                total += card.value()

        # Downgrade aces from 11 to 1 as needed to avoid bust
        while total > 21 and aces > 0:
            total -= 10  # Convert one Ace from 11 to 1
            aces -= 1

        return total

    def is_blackjack(self) -> bool:
        """
        Check if hand is a natural blackjack.
        Exactly 2 cards: one Ace and one 10-value card.
        """
        if len(self.cards) != 2:
            return False

        has_ace = any(card.rank == Rank.ACE for card in self.cards)
        has_ten_value = any(
            card.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING)
            for card in self.cards
        )

        return has_ace and has_ten_value

    def is_bust(self) -> bool:
        """Check if hand busts (total > 21)."""
        return self.total() > 21

    def card_count(self) -> int:
        """Return number of cards in hand."""
        return len(self.cards)

    def cards_list(self) -> List[Card]:
        """Return copy of cards list."""
        return self.cards.copy()

    def __len__(self) -> int:
        return len(self.cards)

    def __str__(self) -> str:
        cards_str = " ".join(card.display() for card in self.cards)
        return f"Hand({cards_str}) Total: {self.total()}"

    def __repr__(self) -> str:
        return f"Hand({len(self.cards)} cards, total={self.total()})"
