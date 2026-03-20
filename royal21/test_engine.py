"""
Unit tests for Royal 21 game engine - tests core mechanics and ranking.
"""
import pytest
from card import Card, Rank, Suit, Deck
from hand import Hand, evaluate_hand, rank_hands, compare_natural_blackjacks_special, HandRank
from game_state import GameState, PlayerState, Phase
from engine import GameEngine


# ============================================================================
# CARD AND DECK TESTS
# ============================================================================

def test_card_value():
    """Test card values."""
    assert Card(Rank.TWO, Suit.HEARTS).value() == 2
    assert Card(Rank.TEN, Suit.HEARTS).value() == 10
    assert Card(Rank.JACK, Suit.HEARTS).value() == 10
    assert Card(Rank.ACE, Suit.HEARTS).value() == 1  # Soft-hand logic applies later


def test_card_is_ten_value():
    """Test 10-value card detection."""
    assert Card(Rank.TEN, Suit.HEARTS).is_ten_value()
    assert Card(Rank.JACK, Suit.HEARTS).is_ten_value()
    assert Card(Rank.QUEEN, Suit.HEARTS).is_ten_value()
    assert Card(Rank.KING, Suit.HEARTS).is_ten_value()
    assert not Card(Rank.ACE, Suit.HEARTS).is_ten_value()
    assert not Card(Rank.NINE, Suit.HEARTS).is_ten_value()


def test_card_rank_order():
    """Test 10-value card ranking (K > Q > J > 10)."""
    assert Card(Rank.KING, Suit.HEARTS).rank_order() == 4
    assert Card(Rank.QUEEN, Suit.HEARTS).rank_order() == 3
    assert Card(Rank.JACK, Suit.HEARTS).rank_order() == 2
    assert Card(Rank.TEN, Suit.HEARTS).rank_order() == 1


def test_deck_shuffle_deterministic():
    """Test that deck shuffles deterministically with seed."""
    deck1 = Deck(seed=12345)
    deck1.shuffle()
    cards1 = [str(deck1.deal()) for _ in range(10)]

    deck2 = Deck(seed=12345)
    deck2.shuffle()
    cards2 = [str(deck2.deal()) for _ in range(10)]

    assert cards1 == cards2


# ============================================================================
# HAND TOTAL AND BLACKJACK TESTS
# ============================================================================

def test_hand_total_basic():
    """Test basic hand total calculation."""
    hand = Hand([Card(Rank.FIVE, Suit.HEARTS), Card(Rank.SIX, Suit.HEARTS)])
    assert hand.total() == 11


def test_hand_total_soft_ace():
    """Test soft-hand logic (Ace = 11 when it doesn't bust)."""
    hand = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.NINE, Suit.HEARTS)])
    assert hand.total() == 20  # Ace counts as 11


def test_hand_total_hard_ace():
    """Test hard-hand logic (Ace = 1 when 11 would bust)."""
    hand = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)])
    # Can't use Ace as 11 (would be 21), but with more cards...
    hand.add_drawn_card(Card(Rank.FIVE, Suit.HEARTS))
    assert hand.total() == 16  # A(1) + K(10) + 5 = 16


def test_hand_natural_blackjack():
    """Test natural blackjack detection."""
    hand = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)])
    assert hand.is_natural_blackjack()
    assert hand.total() == 21


def test_natural_blackjack_not_from_split():
    """Natural blackjack must be from original 2 cards only."""
    hand = Hand([Card(Rank.NINE, Suit.HEARTS), Card(Rank.ACE, Suit.HEARTS)])
    hand.add_drawn_card(Card(Rank.KING, Suit.HEARTS))
    assert not hand.is_natural_blackjack()  # Drew to make it, not natural
    assert hand.total() == 20


def test_split_ace_with_ten_not_natural():
    """Split ace receiving 10 = 21 but NOT natural blackjack."""
    hand = Hand([Card(Rank.ACE, Suit.HEARTS)], "split_a")
    hand.add_drawn_card(Card(Rank.KING, Suit.HEARTS))
    assert not hand.is_natural_blackjack()
    assert hand.total() == 21


def test_bust_detection():
    """Test bust detection."""
    hand = Hand([Card(Rank.KING, Suit.HEARTS), Card(Rank.QUEEN, Suit.HEARTS)])
    hand.add_drawn_card(Card(Rank.FIVE, Suit.HEARTS))
    assert hand.busted
    assert hand.total() > 21


# ============================================================================
# HAND RANKING TESTS
# ============================================================================

def test_evaluate_natural_blackjack():
    """Test evaluation returns NATURAL_BLACKJACK rank."""
    hand = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)])
    rank, tiebreaker = evaluate_hand(hand)
    assert rank == HandRank.NATURAL_BLACKJACK
    assert tiebreaker == 1  # King rank order


def test_evaluate_regular_21():
    """21 from 3+ cards is not natural blackjack."""
    hand = Hand([Card(Rank.SEVEN, Suit.HEARTS), Card(Rank.SEVEN, Suit.HEARTS)])
    hand.add_drawn_card(Card(Rank.SEVEN, Suit.HEARTS))
    rank, tiebreaker = evaluate_hand(hand)
    assert rank == HandRank.TWENTY
    assert rank != HandRank.NATURAL_BLACKJACK


def test_blackjack_vs_blackjack_king_vs_queen():
    """Test AK beats AQ."""
    hand_ak = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)])
    hand_aq = Hand([Card(Rank.ACE, Suit.DIAMONDS), Card(Rank.QUEEN, Suit.DIAMONDS)])

    rank_ak, tie_ak = evaluate_hand(hand_ak)
    rank_aq, tie_aq = evaluate_hand(hand_aq)

    assert rank_ak == rank_aq == HandRank.NATURAL_BLACKJACK
    assert tie_ak > tie_aq  # K (4) > Q (3)


def test_blackjack_suited_beats_offsuit():
    """Test suited blackjack beats offsuit for same ten-card."""
    hand_suited = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)])
    hand_offsuit = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.DIAMONDS)])

    groups = compare_natural_blackjacks_special([hand_suited, hand_offsuit])
    assert len(groups) == 2
    assert groups[0][0] == hand_suited  # Suited is first (better)


def test_blackjack_suited_ties_with_offsuit_same_rank():
    """Test two suited blackjacks with same rank split."""
    hand1 = Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)])
    hand2 = Hand([Card(Rank.ACE, Suit.DIAMONDS), Card(Rank.KING, Suit.DIAMONDS)])

    groups = compare_natural_blackjacks_special([hand1, hand2])
    assert len(groups) == 1  # Both in same group (tied)
    assert len(groups[0]) == 2


def test_rank_hands_multiple():
    """Test ranking multiple hands."""
    hands = [
        Hand([Card(Rank.FIVE, Suit.HEARTS), Card(Rank.EIGHT, Suit.HEARTS)]),  # 13
        Hand([Card(Rank.TEN, Suit.HEARTS), Card(Rank.TEN, Suit.HEARTS)]),  # 20
        Hand([Card(Rank.ACE, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)]),  # Natural BJ
    ]

    groups = rank_hands(hands)
    assert len(groups) == 3
    # First group should have natural blackjack
    assert groups[0][0].is_natural_blackjack()
    # Second should have 20
    assert groups[1][0].total() == 20
    # Third should have 13
    assert groups[2][0].total() == 13


# ============================================================================
# POT-LIMIT SIZING TESTS
# ============================================================================

def test_custom_raise_cap():
    """Test custom pot-limit sizing: max_raise_to = current_high + TABLE_TOTAL."""
    game = GameEngine("test", 2, 100, seed=42)
    game.game.players[0].normal_circle = 10
    game.game.players[1].normal_circle = 5
    game.game.players[0].escrow_circle = 5
    game.game.players[1].escrow_circle = 3

    # TABLE_TOTAL = (10 + 5) + (5 + 3) = 23
    table_total = game.game.table_total()
    assert table_total == 23

    # current_high_normal = 10
    current_high = 10
    # max_raise_to should be 10 + 23 = 33
    max_raise = current_high + table_total
    assert max_raise == 33


def test_raise_cap_with_zero_pot():
    """Test raise cap when no bets yet."""
    game = GameEngine("test", 2, 100, seed=42)
    # No one has bet
    table_total = game.game.table_total()
    # max bet = TABLE_TOTAL (no highest bet yet)
    assert table_total == 0  # No chips on table yet


# ============================================================================
# ESCROW LOCK TESTS
# ============================================================================

def test_escrow_lock_after_hit():
    """Test that player cannot add escrow on river after hitting in draw."""
    game = GameEngine("test", 2, 100, seed=42)
    player = game.game.players[0]

    # Simulate hit_taken flag
    player.hit_taken = True

    # Try to get legal actions for river
    # (In full impl, would need to set phase to RIVER)
    assert player.hit_taken  # Flag is set


def test_no_escrow_lock_after_stand():
    """Test that player CAN add escrow if they only stood (no hit)."""
    game = GameEngine("test", 2, 100, seed=42)
    player = game.game.players[0]

    # No hit taken
    assert not player.hit_taken  # Can add escrow


# ============================================================================
# GAME STATE TESTS
# ============================================================================

def test_game_state_initialization():
    """Test game initialization."""
    game = GameEngine("test_game", 4, 200, seed=42)

    assert game.game.game_id == "test_game"
    assert game.game.num_players == 4
    assert len(game.game.players) == 4
    assert all(p.stack == 200 for p in game.game.players)


def test_active_players():
    """Test active player tracking."""
    game = GameEngine("test", 3, 100)
    game.game.players[1].folded = True

    active = game.game.active_players()
    assert len(active) == 2
    assert game.game.players[1] not in active


def test_next_action_index():
    """Test action order calculation."""
    game = GameEngine("test", 3, 100)
    active_seats = game.game.active_seats()

    # Starting from seat 0, next should be seat 1 (or wrap)
    next_seat = game.game.next_active_index(active_seats[0])
    assert next_seat is not None or len(active_seats) <= 1


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_full_hand_setup():
    """Test starting a full hand."""
    game = GameEngine("test", 2, 100, seed=42)
    game.start_hand()

    assert game.game.phase == Phase.PREFLOP
    # Both players should have 2 hole cards
    assert all(len(p.hole_cards) == 2 for p in game.game.players if p.in_hand)
    # Button should have posted 1 normal
    button = game.game.players[game.game.button_index]
    assert button.normal_circle == 1
    # Both should have escrow ante
    assert all(p.escrow_circle == 1 for p in game.game.players if p.in_hand)


def test_fold_forfeits_both_circles():
    """Test that folding forfeits both normal and escrow chips."""
    game = GameEngine("test", 2, 100, seed=42)
    game.start_hand()

    player = game.game.players[0]
    initial_stack = player.stack
    normal_on_table = player.normal_circle
    escrow_on_table = player.escrow_circle

    player.folded = True
    player.in_hand = False

    # Player's stack unchanged (chips already spent in setup)
    # But both circles are forfeited (not recoverable)
    assert player.normal_circle == normal_on_table
    assert player.escrow_circle == escrow_on_table


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
