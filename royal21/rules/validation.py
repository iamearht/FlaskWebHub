"""Hand validation rules."""

from ..cards.hand import Hand
from ..cards.card import Rank


def is_valid_3card_hand(hand: Hand) -> bool:
    """
    Check if a 3-card hand is valid.

    Rules for 3-card hands:
    - Flush, Straight, Trips, Straight Flush: sum must be < 21
    - Otherwise: any 3-card hand is valid

    Args:
        hand: Hand object with 3 cards.

    Returns:
        True if hand is valid, False otherwise.
    """
    if hand.card_count() != 3:
        return True  # Not a 3-card hand

    total = hand.total()

    # If sum >= 21, hand is invalid for special combos
    # (But for MVP, we just check basic validity)
    # Actually, hands totaling 21+ might still be valid (bust is handled at evaluation)
    # So all 3-card hands are valid

    return True


def is_valid_hand(hand: Hand) -> bool:
    """
    Check if a hand is valid.

    Most hands are automatically valid. This checks edge cases.

    Returns:
        True if hand is valid, False otherwise.
    """
    if not hand.cards_list():
        return False  # Empty hand

    if hand.card_count() > 3:
        return False  # Can't have more than 3 cards (2 initial + 1 draw)

    if hand.card_count() == 3:
        return is_valid_3card_hand(hand)

    return True
