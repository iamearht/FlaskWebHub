"""
Hand evaluation and ranking logic for Royal 21.
"""
from enum import IntEnum
from typing import List, Optional, Tuple
from card import Card, Rank


class HandRank(IntEnum):
    """Hand rankings (higher is better)."""
    BUST = 0
    TWENTY = 20
    NINETEEN = 19
    EIGHTEEN = 18
    SEVENTEEN = 17
    SIXTEEN = 16
    FIFTEEN = 15
    FOURTEEN = 14
    THIRTEEN = 13
    TWELVE = 12
    ELEVEN = 11
    TEN = 10
    NATURAL_BLACKJACK = 999  # Special rank for natural blackjack


class Hand:
    """Represents a single blackjack hand (original or split)."""

    def __init__(self, hole_cards: List[Card], hand_id: str = "original"):
        self.hand_id = hand_id  # "original", "split_a", "split_b", etc.
        self.hole_cards = hole_cards.copy()
        self.drawn_cards: List[Card] = []
        self.busted = False
        self.stood = False
        self.doubled = False
        self.revealed_card: Optional[Card] = None  # Only for original hand

    def add_drawn_card(self, card: Card):
        """Add a drawn card."""
        self.drawn_cards.append(card)
        self._check_bust()

    def _check_bust(self):
        """Determine if hand is busted (total > 21)."""
        self.busted = self.total() > 21

    def total(self) -> int:
        """Calculate best hand total (soft-hand logic for aces)."""
        all_cards = self.hole_cards + self.drawn_cards
        if not all_cards:
            return 0

        # Count aces and non-ace value
        aces = sum(1 for card in all_cards if card.is_ace())
        total = sum(card.value() for card in all_cards)  # All aces = 1 initially

        # Upgrade one ace to 11 if it doesn't bust
        if aces > 0 and total + 10 <= 21:
            total += 10

        return total

    def all_cards(self) -> List[Card]:
        """Return all cards in hand."""
        return self.hole_cards + self.drawn_cards

    def card_count(self) -> int:
        """Total number of cards."""
        return len(self.hole_cards) + len(self.drawn_cards)

    def is_natural_blackjack(self) -> bool:
        """
        Check if this hand is a natural blackjack:
        - Exactly 2 cards
        - One is an Ace
        - One is a 10-value card
        - Must be from original 2-card hand (no draws, not a split-ace 21)
        """
        # Must be exactly 2 cards in hole cards, no drawn cards
        if len(self.hole_cards) != 2 or len(self.drawn_cards) > 0:
            return False

        # One ace, one 10-value
        has_ace = any(card.is_ace() for card in self.hole_cards)
        has_ten = any(card.is_ten_value() for card in self.hole_cards)

        return has_ace and has_ten

    def __repr__(self) -> str:
        cards_str = ", ".join(str(c) for c in self.all_cards())
        total = self.total()
        status = "BUST" if self.busted else f"Total {total}"
        return f"Hand({self.hand_id}: [{cards_str}] -> {status})"


def evaluate_hand(hand: Hand) -> Tuple[HandRank, int]:
    """
    Evaluate a single hand and return (rank, tiebreaker).

    Returns:
        (HandRank, tiebreaker_value)
        - For natural blackjack: (NATURAL_BLACKJACK, ten_card_rank_order)
        - For bust: (BUST, 0)
        - For other: (total, 0) or (21, 0) etc.
    """
    if hand.busted:
        return (HandRank.BUST, 0)

    if hand.is_natural_blackjack():
        # Natural blackjack: use ten-card rank order as tiebreaker
        ten_card = next(c for c in hand.hole_cards if c.is_ten_value())
        return (HandRank.NATURAL_BLACKJACK, ten_card.rank_order())

    total = hand.total()
    return (HandRank(total) if total <= 21 else HandRank.BUST, 0)


def rank_hands(hands: List[Hand]) -> List[List[Hand]]:
    """
    Rank multiple hands and return groups of tied hands.

    Returns:
        List of hand groups, where each group contains tied hands.
        Higher-ranked hands come first.
    """
    if not hands:
        return []

    # Evaluate each hand
    hand_ranks = [(hand, evaluate_hand(hand)) for hand in hands]

    # Sort by rank (descending), then by tiebreaker (descending)
    hand_ranks.sort(key=lambda x: (x[1][0], x[1][1]), reverse=True)

    # Group tied hands
    groups = []
    current_group = []
    current_rank = None

    for hand, rank in hand_ranks:
        if current_rank is None or rank == current_rank:
            current_group.append(hand)
            current_rank = rank
        else:
            groups.append(current_group)
            current_group = [hand]
            current_rank = rank

    if current_group:
        groups.append(current_group)

    return groups


def compare_natural_blackjacks_special(hands: List[Hand]) -> List[List[Hand]]:
    """
    Special ranking for when multiple players have natural blackjack.

    Ranking:
    1. Ten-card rank (K > Q > J > 10)
    2. Suited vs offsuit (suited wins)
    3. If still tied, split equally

    Returns:
        List of hand groups (tied hands grouped)
    """
    if not hands or not all(h.is_natural_blackjack() for h in hands):
        return []

    # Extract ten-card and ace for each hand
    hand_data = []
    for hand in hands:
        ace = next(c for c in hand.hole_cards if c.is_ace())
        ten = next(c for c in hand.hole_cards if c.is_ten_value())
        is_suited = ace.suit == ten.suit
        hand_data.append((hand, ten.rank_order(), is_suited))

    # Sort by ten-rank (desc), then by suited (True > False)
    hand_data.sort(key=lambda x: (x[1], x[2]), reverse=True)

    # Group by ranking
    groups = []
    current_group = []
    current_key = None

    for hand, ten_rank, is_suited in hand_data:
        key = (ten_rank, is_suited)
        if current_key is None or key == current_key:
            current_group.append(hand)
            current_key = key
        else:
            groups.append(current_group)
            current_group = [hand]
            current_key = key

    if current_group:
        groups.append(current_group)

    return groups
