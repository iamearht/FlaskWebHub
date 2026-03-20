from enum import IntEnum
from typing import Tuple
from .card import Card, Rank
from .hand import Hand


class HandRank(IntEnum):
    """Hand ranking from lowest to highest."""
    BUST = 0
    TWENTY = 1
    THREE_CARD_TWENTYONE = 2
    OFFSUIT_BLACKJACK = 3
    FLUSH = 4
    STRAIGHT = 5
    SUITED_BLACKJACK = 6
    TRIPS = 7
    STRAIGHT_FLUSH = 8
    TWENTYONE = 9  # 3+ card 21 (not natural blackjack)
    NATURAL_BLACKJACK = 10


def get_card_rank_order() -> dict[Rank, int]:
    """
    Returns a mapping of card ranks to their numeric order for straight detection.
    Ace can be 1 (low) or 14 (high).
    """
    return {
        Rank.TWO: 2,
        Rank.THREE: 3,
        Rank.FOUR: 4,
        Rank.FIVE: 5,
        Rank.SIX: 6,
        Rank.SEVEN: 7,
        Rank.EIGHT: 8,
        Rank.NINE: 9,
        Rank.TEN: 10,
        Rank.JACK: 11,
        Rank.QUEEN: 12,
        Rank.KING: 13,
        Rank.ACE: 14,  # Ace high
    }


def is_flush(cards: list[Card]) -> bool:
    """Check if cards form a flush (all same suit)."""
    if len(cards) < 3:
        return False
    suit = cards[0].suit
    return all(card.suit == suit for card in cards)


def is_straight(cards: list[Card]) -> bool:
    """
    Check if cards form a straight (consecutive ranks).
    Works for 3+ cards. Ace can be high or low.
    """
    if len(cards) < 3:
        return False

    rank_order = get_card_rank_order()
    ranks_nums = sorted([rank_order[card.rank] for card in cards])

    # Check for standard straight
    for i in range(len(ranks_nums) - 1):
        if ranks_nums[i + 1] - ranks_nums[i] != 1:
            return False
    return True


def is_trips(cards: list[Card]) -> bool:
    """Check if cards contain three of a kind."""
    if len(cards) < 3:
        return False
    ranks = [card.rank for card in cards]
    return len(set(ranks)) < len(ranks)  # Duplicate ranks exist


def has_ace_and_ten_value(cards: list[Card]) -> bool:
    """Check if hand contains an Ace and a 10-value card."""
    has_ace = any(card.rank == Rank.ACE for card in cards)
    has_ten = any(
        card.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING)
        for card in cards
    )
    return has_ace and has_ten


def get_ten_value_card(cards: list[Card]) -> Card | None:
    """Get the 10-value card from hand (if it exists)."""
    for card in cards:
        if card.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING):
            return card
    return None


def get_suited_blackjack_cards(cards: list[Card]) -> Tuple[Card, Card] | None:
    """
    Get Ace and 10-value card if they form a suited blackjack.
    Returns (Ace, TenValue) or None.
    """
    ace = None
    ten_value = None

    for card in cards:
        if card.rank == Rank.ACE:
            ace = card
        elif card.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING):
            ten_value = card

    if ace and ten_value and ace.suit == ten_value.suit:
        return (ace, ten_value)
    return None


def get_offsuit_blackjack_cards(cards: list[Card]) -> Tuple[Card, Card] | None:
    """
    Get Ace and 10-value card if they form an off-suit blackjack.
    Returns (Ace, TenValue) or None.
    """
    ace = None
    ten_value = None

    for card in cards:
        if card.rank == Rank.ACE:
            ace = card
        elif card.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING):
            ten_value = card

    if ace and ten_value and ace.suit != ten_value.suit:
        return (ace, ten_value)
    return None


def ten_value_rank(card: Card) -> int:
    """Get numeric rank for 10-value cards for tiebreaking."""
    ranking = {
        Rank.ACE: 4,
        Rank.KING: 3,
        Rank.QUEEN: 2,
        Rank.JACK: 1,
        Rank.TEN: 0,
    }
    return ranking.get(card.rank, -1)


def evaluate_hand(hand: Hand) -> Tuple[HandRank, Tuple]:
    """
    Evaluate a hand and return (rank, tiebreaker).

    Args:
        hand: Hand object to evaluate.

    Returns:
        (HandRank, tiebreaker_tuple) where tiebreaker is used to break ties
        between hands of the same rank.
    """
    cards = hand.cards_list()
    total = hand.total()

    # Bust: automatic loss
    if total > 21:
        return (HandRank.BUST, ())

    # Natural Blackjack: exactly 2 cards, one Ace, one 10-value
    if hand.is_blackjack():
        ten_card = get_ten_value_card(cards)
        # Tiebreaker: rank of 10-value card (K > Q > J > 10)
        tiebreak = (ten_value_rank(ten_card),)
        return (HandRank.NATURAL_BLACKJACK, tiebreak)

    # Total 21 with 3+ cards (not natural blackjack)
    if total == 21:
        return (HandRank.TWENTYONE, ())

    # 3-Card Combinations (only valid if sum < 21)
    if len(cards) == 3 and total < 21:
        # Straight Flush (3 cards, sequential, same suit, sum < 21)
        if is_straight(cards) and is_flush(cards):
            # Tiebreaker: highest card in straight
            high_card = max(card.rank for card in cards)
            return (HandRank.STRAIGHT_FLUSH, (high_card.value,))

        # Trips (three of a kind, sum < 21)
        if is_trips(cards):
            return (HandRank.TRIPS, ())

        # Suited Blackjack (A + 10-value, same suit, sum < 21)
        suited_bj = get_suited_blackjack_cards(cards)
        if suited_bj:
            ace, ten = suited_bj
            # Tiebreaker: rank of 10-value card
            return (HandRank.SUITED_BLACKJACK, (ten_value_rank(ten),))

        # Straight (3 cards, sequential, sum < 21)
        if is_straight(cards):
            # Tiebreaker: highest card
            high_card = max(card.rank for card in cards)
            return (HandRank.STRAIGHT, (high_card.value,))

        # Flush (3 cards, same suit, sum < 21)
        if is_flush(cards):
            # Tiebreaker: high cards in order (like poker)
            high_cards = sorted(
                [card.rank.value for card in cards if card.rank != Rank.ACE],
                reverse=True
            )
            if any(c.rank == Rank.ACE for c in cards):
                high_cards = [11] + high_cards
            return (HandRank.FLUSH, tuple(high_cards))

        # Off-suit Blackjack (A + 10-value, different suits, sum < 21)
        offsuit_bj = get_offsuit_blackjack_cards(cards)
        if offsuit_bj:
            ace, ten = offsuit_bj
            return (HandRank.OFFSUIT_BLACKJACK, (ten_value_rank(ten),))

        # 3-card 21 (3 cards totaling 21, no special combo)
        if total == 21:
            return (HandRank.THREE_CARD_TWENTYONE, ())

    # Total 20 (any number of cards)
    if total == 20:
        return (HandRank.TWENTY, ())

    # Fallback: other totals below 20 (shouldn't reach here in normal play)
    return (HandRank.TWENTY, ())


def compare_hands(hand1: Hand, hand2: Hand) -> int:
    """
    Compare two hands.

    Args:
        hand1: First hand.
        hand2: Second hand.

    Returns:
        1 if hand1 wins, -1 if hand2 wins, 0 if tie.
    """
    rank1, tie1 = evaluate_hand(hand1)
    rank2, tie2 = evaluate_hand(hand2)

    if rank1 > rank2:
        return 1
    elif rank1 < rank2:
        return -1
    else:
        # Same rank; compare tiebreakers
        if tie1 > tie2:
            return 1
        elif tie1 < tie2:
            return -1
        else:
            return 0  # Tie
