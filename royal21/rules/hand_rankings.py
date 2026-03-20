"""Hand ranking definitions, evaluation, and comparison logic."""

from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.card import Card


# Poker rank values for straight detection and tiebreaking (NOT blackjack values)
_POKER_RANKS = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
}


class HandRank(IntEnum):
    """Hand rank enum — higher value = stronger hand."""
    BUST = 0
    HIGH_TOTAL = 1
    OFFSUIT_BJ = 2
    FLUSH = 3
    STRAIGHT = 4
    SUITED_BJ = 5
    TRIPS = 6
    STRAIGHT_FLUSH = 7


RANK_DISPLAY = {
    HandRank.BUST: "Bust",
    HandRank.HIGH_TOTAL: "High Total",
    HandRank.OFFSUIT_BJ: "Offsuit Blackjack",
    HandRank.FLUSH: "Flush",
    HandRank.STRAIGHT: "Straight",
    HandRank.SUITED_BJ: "Suited Blackjack",
    HandRank.TRIPS: "Trips",
    HandRank.STRAIGHT_FLUSH: "Straight Flush",
}

# Keep old name as alias for backwards compatibility with any imports
HandRankName = HandRank


def poker_rank(card) -> int:
    """Return the poker rank value of a card (2=2 … K=13, A=14)."""
    return _POKER_RANKS[card.rank]


def calculate_hand_total(cards) -> int:
    """Calculate hand total using blackjack rules (Aces downgrade 11→1 to avoid bust)."""
    if not cards:
        return 0
    total = sum(card.value for card in cards)
    ace_count = sum(1 for c in cards if c.rank == 'A')
    while total > 21 and ace_count > 0:
        total -= 10
        ace_count -= 1
    return total


def _is_three_card_straight(cards) -> tuple:
    """Check if exactly 3 cards form a straight.

    Returns (is_straight: bool, top_card_rank: int).
    Top card uses poker rank (A=14), except A-2-3 where top=3 (Ace plays low).
    """
    if len(cards) != 3:
        return False, 0

    ranks = sorted([poker_rank(c) for c in cards])

    if len(set(ranks)) != 3:
        return False, 0  # Duplicate ranks — not a straight

    # Normal straight: three consecutive ranks
    if ranks[2] - ranks[0] == 2:
        return True, ranks[2]

    # A-low straight: A-2-3 (poker ranks [2, 3, 14])
    if ranks == [2, 3, 14]:
        return True, 3  # Top card = 3; Ace plays as 1

    return False, 0


def evaluate_hand(cards) -> tuple:
    """Evaluate a hand and return a comparable tuple.

    Format: (HandRank_int, tiebreaker1, tiebreaker2, ...).
    Tuples are directly comparable with Python's built-in comparison — higher is better.

    Hand priority (3 cards, highest first):
      Straight Flush > Trips > Straight > Flush > High Total

    Special 2-card hands:
      Suited BJ > Offsuit BJ > High Total

    A bust hand (total > 21) is always rank 0 regardless of card pattern.
    """
    if not cards:
        return (HandRank.BUST, 0)

    total = calculate_hand_total(cards)

    # Bust: cannot qualify for any special rank
    if total > 21:
        return (HandRank.BUST, 0)

    n = len(cards)

    if n == 2:
        # 2-card hands: BJ variants or plain total
        has_ace = any(c.rank == 'A' for c in cards)
        ten_val_cards = [c for c in cards if c.value == 10 and c.rank != 'A']

        if has_ace and ten_val_cards:
            ten_card = ten_val_cards[0]
            ace = next(c for c in cards if c.rank == 'A')
            ten_rank = poker_rank(ten_card)
            if ace.suit == ten_card.suit:
                return (HandRank.SUITED_BJ, ten_rank)
            else:
                return (HandRank.OFFSUIT_BJ, ten_rank)

        return (HandRank.HIGH_TOTAL, total)

    if n == 3:
        all_same_suit = len(set(c.suit for c in cards)) == 1
        is_straight, straight_top = _is_three_card_straight(cards)
        is_trips = len(set(c.rank for c in cards)) == 1

        if is_straight and all_same_suit:
            return (HandRank.STRAIGHT_FLUSH, straight_top)

        if is_trips:
            return (HandRank.TRIPS, poker_rank(cards[0]))

        if is_straight:
            return (HandRank.STRAIGHT, straight_top)

        if all_same_suit:
            # Flush tiebreaker: highest card, then 2nd, then 3rd
            r1, r2, r3 = sorted([poker_rank(c) for c in cards], reverse=True)
            return (HandRank.FLUSH, r1, r2, r3)

        return (HandRank.HIGH_TOTAL, total)

    # Fallback for unexpected card counts
    return (HandRank.HIGH_TOTAL, total)


def hand_display(cards, eval_result: tuple) -> str:
    """Return a human-readable description of an evaluated hand."""
    rank = HandRank(eval_result[0])
    cards_str = " ".join(c.display for c in cards)
    label = RANK_DISPLAY.get(rank, "Unknown")

    if rank == HandRank.BUST:
        raw_total = sum(c.value for c in cards)
        return f"Bust ({raw_total}) [{cards_str}]"
    elif rank == HandRank.HIGH_TOTAL:
        return f"{label}: {eval_result[1]} [{cards_str}]"
    else:
        return f"{label} [{cards_str}]"


def find_winners(evaluations: dict) -> list:
    """Return the seat(s) with the best hand from an evaluations dict.

    Args:
        evaluations: {seat_int: evaluate_hand_result_tuple}

    Returns:
        List of seat ints with the highest evaluation (multiple = tie/split).
    """
    if not evaluations:
        return []
    best = max(evaluations.values())
    return sorted(seat for seat, ev in evaluations.items() if ev == best)
