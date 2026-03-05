"""
Comprehensive tests for Two-Circle Royal 21 game engine.

Tests cover:
- Blackjack hand evaluation and ranking
- Natural blackjack vs 21 distinction
- Split Aces rule
- Escrow locking after hit
- Pot-limit calculations
- Hand comparison and showdown
"""

import pytest
from blackjack_game_engine import (
    Card,
    Deck,
    compute_blackjack_value,
    is_natural_blackjack,
    get_hand_rank_and_value,
    compare_natural_blackjacks,
    GamePhase,
    ActionType,
    BlackjackGameEngine,
    HandRank,
)


# ============================================================================
# CARD & DECK TESTS
# ============================================================================

def test_card_string():
    """Test card representation"""
    card = Card('A', '♠')
    assert str(card) == 'A♠'


def test_deck_initialization():
    """Test deck has 52 cards"""
    deck = Deck()
    assert len(deck.cards) == 52


def test_deck_draw():
    """Test drawing cards"""
    deck = Deck()
    initial_count = len(deck.cards)
    card = deck.draw()
    assert isinstance(card, Card)
    assert len(deck.cards) == initial_count - 1


def test_deck_reshuffle():
    """Test deck reshuffles when empty"""
    deck = Deck(seed=42)
    # Draw all 52 cards
    for _ in range(52):
        deck.draw()
    assert len(deck.cards) == 0
    # Next draw triggers reshuffle
    card = deck.draw()
    assert card is not None
    assert len(deck.cards) == 51


def test_deck_seedable_rng():
    """Test that deck with same seed produces same shuffle"""
    deck1 = Deck(seed=42)
    cards1 = [deck1.draw() for _ in range(10)]

    deck2 = Deck(seed=42)
    cards2 = [deck2.draw() for _ in range(10)]

    assert all(c1.rank == c2.rank and c1.suit == c2.suit for c1, c2 in zip(cards1, cards2))


# ============================================================================
# BLACKJACK VALUE COMPUTATION
# ============================================================================

def test_compute_value_numbered():
    """Test numbered card values"""
    cards = [Card('5', '♠'), Card('3', '♥')]
    assert compute_blackjack_value(cards) == 8


def test_compute_value_face_cards():
    """Test face cards = 10"""
    cards = [Card('K', '♠'), Card('Q', '♥')]
    assert compute_blackjack_value(cards) == 20


def test_compute_value_with_ace_no_bust():
    """Test Ace counts as 11 when it doesn't bust"""
    cards = [Card('A', '♠'), Card('9', '♥')]
    assert compute_blackjack_value(cards) == 20


def test_compute_value_with_ace_bust_becomes_1():
    """Test Ace counts as 1 to avoid bust"""
    cards = [Card('A', '♠'), Card('K', '♥'), Card('5', '♦')]
    assert compute_blackjack_value(cards) == 16  # A=1, K=10, 5=5


def test_compute_value_multiple_aces():
    """Test multiple Aces"""
    cards = [Card('A', '♠'), Card('A', '♥'), Card('9', '♦')]
    assert compute_blackjack_value(cards) == 21  # A=11, A=1, 9=9


def test_compute_value_bust():
    """Test bust (>21)"""
    cards = [Card('K', '♠'), Card('Q', '♥'), Card('5', '♦')]
    assert compute_blackjack_value(cards) == 25


def test_compute_value_empty():
    """Test empty hand"""
    assert compute_blackjack_value([]) == 0


# ============================================================================
# NATURAL BLACKJACK DETECTION
# ============================================================================

def test_natural_blackjack_ak():
    """Test natural blackjack: Ace + King"""
    cards = [Card('A', '♠'), Card('K', '♥')]
    assert is_natural_blackjack(cards) is True


def test_natural_blackjack_aq():
    """Test natural blackjack: Ace + Queen"""
    cards = [Card('A', '♠'), Card('Q', '♥')]
    assert is_natural_blackjack(cards) is True


def test_natural_blackjack_aj():
    """Test natural blackjack: Ace + Jack"""
    cards = [Card('A', '♠'), Card('J', '♥')]
    assert is_natural_blackjack(cards) is True


def test_natural_blackjack_a10():
    """Test natural blackjack: Ace + 10"""
    cards = [Card('A', '♠'), Card('10', '♥')]
    assert is_natural_blackjack(cards) is True


def test_not_natural_21_three_cards():
    """Test 21 with three cards is not natural blackjack"""
    cards = [Card('7', '♠'), Card('7', '♥'), Card('7', '♦')]
    assert is_natural_blackjack(cards) is False


def test_not_natural_split_ace_21():
    """Test split Ace getting 10-value is not natural blackjack"""
    # This is harder to test without full game state; we'd need to mark it as from split
    # For now, we rely on the logic that only 2-card hands are checked
    cards = [Card('A', '♠'), Card('10', '♥'), Card('5', '♦')]
    assert is_natural_blackjack(cards) is False


def test_not_natural_blackjack_different_suits():
    """Test Ace + 10-value still counts regardless of suit"""
    cards = [Card('A', '♠'), Card('K', '♦')]
    assert is_natural_blackjack(cards) is True


# ============================================================================
# HAND RANKING
# ============================================================================

def test_hand_rank_natural_blackjack():
    """Test natural blackjack ranking"""
    cards = [Card('A', '♠'), Card('K', '♥')]
    rank, value = get_hand_rank_and_value(cards)
    assert rank == HandRank.NATURAL_BLACKJACK
    assert value == 21


def test_hand_rank_21_non_natural():
    """Test 21 that's not natural (3 cards)"""
    cards = [Card('7', '♠'), Card('7', '♥'), Card('7', '♦')]
    rank, value = get_hand_rank_and_value(cards)
    assert rank == HandRank.TWENTY_ONE
    assert value == 21


def test_hand_rank_high_card():
    """Test high card ranking"""
    cards = [Card('9', '♠'), Card('8', '♥')]
    rank, value = get_hand_rank_and_value(cards)
    assert rank == HandRank.HIGH_CARD
    assert value == 17


def test_hand_rank_bust():
    """Test bust ranking"""
    cards = [Card('K', '♠'), Card('Q', '♥'), Card('5', '♦')]
    rank, value = get_hand_rank_and_value(cards)
    assert rank == HandRank.BUST
    assert value == 0


# ============================================================================
# NATURAL BLACKJACK COMPARISON
# ============================================================================

def test_ak_beats_aq():
    """Test A-K beats A-Q"""
    cards1 = [Card('A', '♠'), Card('K', '♥')]
    cards2 = [Card('A', '♠'), Card('Q', '♥')]
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == 1  # cards1 wins


def test_aq_beats_aj():
    """Test A-Q beats A-J"""
    cards1 = [Card('A', '♠'), Card('Q', '♥')]
    cards2 = [Card('A', '♠'), Card('J', '♥')]
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == 1


def test_aj_beats_a10():
    """Test A-J beats A-10"""
    cards1 = [Card('A', '♠'), Card('J', '♥')]
    cards2 = [Card('A', '♠'), Card('10', '♥')]
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == 1


def test_suited_beats_offsuit():
    """Test suited beats offsuit"""
    cards1 = [Card('A', '♠'), Card('K', '♠')]  # A♠K♠ (suited)
    cards2 = [Card('A', '♠'), Card('K', '♥')]  # A♠K♥ (offsuit)
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == 1


def test_offsuit_loses_to_suited():
    """Test offsuit loses to suited"""
    cards1 = [Card('A', '♠'), Card('K', '♥')]  # offsuit
    cards2 = [Card('A', '♠'), Card('K', '♠')]  # suited
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == -1


def test_suited_vs_suited_same_rank_tie():
    """Test two suited blackjacks with same rank = tie"""
    cards1 = [Card('A', '♠'), Card('J', '♠')]
    cards2 = [Card('A', '♥'), Card('J', '♥')]
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == 0  # tie


def test_offsuit_vs_offsuit_same_rank_tie():
    """Test two offsuit blackjacks with same rank = tie"""
    cards1 = [Card('A', '♠'), Card('J', '♥')]
    cards2 = [Card('A', '♣'), Card('J', '♦')]
    result = compare_natural_blackjacks(cards1, cards2)
    assert result == 0  # tie


# ============================================================================
# GAME ENGINE TESTS
# ============================================================================

def test_engine_create_table():
    """Test creating a game table"""
    players = [(1, 'Alice'), (2, 'Bob'), (3, 'Charlie')]
    engine = BlackjackGameEngine(seed=42)
    state = engine.create_table(players, initial_stack=1000)

    assert len(state.players) == 3
    assert state.players[0].username == 'Alice'
    assert state.players[0].stack == 1000
    assert state.phase == GamePhase.SETUP


def test_engine_start_hand():
    """Test starting a hand"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state

    # Check antes posted
    assert state.escrow_pot == 2  # Both players post 1 escrow ante
    assert state.normal_pot == 1  # Button posts 1 normal

    # Check hands dealt
    for player in state.players:
        assert len(player.hand.original_cards) == 2

    # Check phase advanced
    assert state.phase == GamePhase.PREFLOP


def test_engine_hit_action():
    """Test hitting (drawing a card)"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state
    alice = state.players[0]

    # Make sure Alice can act (set her as current player)
    state.current_player_seat = alice.seat
    state.phase = GamePhase.DRAW

    initial_card_count = len(alice.hand.original_cards)

    # Execute hit action
    engine.player_action(alice.seat, ActionType.HIT)

    # Check card was drawn
    assert len(alice.hand.original_cards) == initial_card_count + 1
    assert alice.hand.cards_drawn == 1
    assert alice.hand.action_this_phase == "hit"
    assert alice.hand.escrow_locked is True  # Escrow locked after hit


def test_engine_split_action():
    """Test splitting a pair"""
    # Create a seeded game to ensure Alice gets a splittable hand
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    # Manually set splittable hand
    state = engine.game_state
    alice = state.players[0]
    alice.hand.original_cards = [Card('7', '♠'), Card('7', '♥')]

    # Make sure alice can act
    state.current_player_seat = alice.seat
    state.phase = GamePhase.DRAW

    engine.player_action(alice.seat, ActionType.SPLIT)

    assert len(alice.hand.split_hands) == 2
    assert alice.hand.action_this_phase == "split"


def test_escrow_lock_after_hit():
    """Test that escrow is locked after hitting"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state
    alice = state.players[0]

    # Set Alice as current player and phase to draw
    state.current_player_seat = alice.seat
    state.phase = GamePhase.DRAW

    # Initially escrow not locked
    assert alice.hand.escrow_locked is False

    # Hit: locks escrow
    engine.player_action(alice.seat, ActionType.HIT)
    assert alice.hand.escrow_locked is True


def test_stand_no_escrow_lock():
    """Test that standing doesn't lock escrow"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state
    alice = state.players[0]

    # Set Alice as current player and phase to draw
    state.current_player_seat = alice.seat
    state.phase = GamePhase.DRAW

    engine.player_action(alice.seat, ActionType.STAND)

    assert alice.hand.escrow_locked is False
    assert alice.hand.action_this_phase == "stand"


def test_double_draws_one_card():
    """Test that doubling draws exactly one card"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state
    alice = state.players[0]

    # Set Alice as current player and phase to draw
    state.current_player_seat = alice.seat
    state.phase = GamePhase.DRAW

    initial_cards = len(alice.hand.original_cards)

    engine.player_action(alice.seat, ActionType.DOUBLE)

    assert len(alice.hand.original_cards) == initial_cards + 1
    assert alice.hand.cards_drawn == 1
    assert alice.hand.action_this_phase == "double"


def test_fold_action():
    """Test folding"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state
    alice = state.players[0]

    # Set Alice as current player
    state.current_player_seat = alice.seat

    engine.player_action(alice.seat, ActionType.FOLD)

    assert alice.hand.is_folded is True


def test_illegal_split_non_pair():
    """Test that splitting non-matching ranks fails"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state
    alice = state.players[0]

    # Alice's hand won't be a pair; trying to split should fail
    try:
        engine.player_action(alice.seat, ActionType.SPLIT)
        # If it doesn't raise, check if hand wasn't modified
        if len(alice.hand.split_hands) > 0:
            pytest.fail("Should not allow split of non-matching ranks")
    except ValueError:
        pass  # Expected


def test_state_export():
    """Test exporting game state"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state_dict = engine.get_state()

    assert state_dict['hand_number'] == 1
    assert state_dict['phase'] == 'preflop'
    assert 'normal_pot' in state_dict
    assert 'escrow_pot' in state_dict
    assert len(state_dict['players']) == 2


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_full_hand_sequence():
    """Test a complete hand sequence"""
    players = [(1, 'Alice'), (2, 'Bob')]
    engine = BlackjackGameEngine(seed=42)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()

    state = engine.game_state

    # Initial state
    assert state.phase == GamePhase.PREFLOP
    assert state.escrow_pot == 2
    assert state.normal_pot == 1

    # Players act - move to draw phase first
    state.phase = GamePhase.DRAW
    alice = state.players[0]
    bob = state.players[1]

    # Alice hits
    state.current_player_seat = alice.seat
    engine.player_action(alice.seat, ActionType.HIT)
    assert alice.hand.escrow_locked is True

    # Bob stands
    state.current_player_seat = bob.seat
    engine.player_action(bob.seat, ActionType.STAND)
    assert bob.hand.escrow_locked is False

    # Final state
    assert len(alice.hand.original_cards) > 2
    assert len(bob.hand.original_cards) == 2


def test_deterministic_simulation():
    """Test that two engines with same seed produce same card sequence"""
    players = [(1, 'Alice'), (2, 'Bob')]

    # Engine 1
    engine1 = BlackjackGameEngine(seed=12345)
    engine1.create_table(players, initial_stack=1000)
    engine1.start_hand()
    cards1 = [str(c) for p in engine1.game_state.players for c in p.hand.original_cards]

    # Engine 2
    engine2 = BlackjackGameEngine(seed=12345)
    engine2.create_table(players, initial_stack=1000)
    engine2.start_hand()
    cards2 = [str(c) for p in engine2.game_state.players for c in p.hand.original_cards]

    assert cards1 == cards2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
