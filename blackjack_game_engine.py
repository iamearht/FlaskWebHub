"""
Two-Circle Royal 21: Hybrid Poker × Blackjack Game Engine

A multiplayer card game with:
- Two chip circles: Normal (main pot) and Escrow (side pot)
- Phases: Setup -> Preflop -> Draw -> River -> Showdown
- Complex hand ranking with natural blackjack
- Proportional escrow settlement
"""

import random
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class GamePhase(Enum):
    """Game phases"""
    SETUP = "setup"  # antes, deal, first action reveal
    PREFLOP = "preflop"  # two-step turns: escrow then normal
    DRAW = "draw"  # hit/stand/double/split
    RIVER = "river"  # two-step turns: escrow then normal
    SHOWDOWN = "showdown"  # evaluate hands and distribute pots
    HAND_OVER = "hand_over"


class ActionType(Enum):
    """Player actions"""
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    ADD_ESCROW = "add_escrow"


class HandRank(Enum):
    """Hand ranking (highest to lowest)"""
    NATURAL_BLACKJACK = 6
    TWENTY_ONE = 5
    HIGH_CARD = 4  # 0-20
    BUST = 0  # >21


# Card constants
CARD_RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
CARD_SUITS = ['♠', '♥', '♦', '♣']
RANK_VALUES = {'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10}

# Configuration
ESCROW_ANTE = 1
BUTTON_ANTE = 1
TABLE_MIN_PLAYERS = 2
TABLE_MAX_PLAYERS = 7
TABLE_DEFAULT_PLAYERS = 7

# Escrow configuration: when a player adds escrow, limit to normal circle size (or make it configurable)
ESCROW_ADD_LIMIT_TYPE = "unlimited"  # "unlimited", "match_normal", or a fixed ratio


# ============================================================================
# CARD & DECK
# ============================================================================

@dataclass
class Card:
    """A playing card"""
    rank: str  # A, 2-10, J, Q, K
    suit: str  # ♠, ♥, ♦, ♣

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return str(self)


class Deck:
    """Single 52-card deck with shuffle"""

    def __init__(self, seed: Optional[int] = None):
        self.cards: List[Card] = []
        self.seed = seed
        self.rng = random.Random(seed)
        self._init_deck()

    def _init_deck(self):
        """Initialize deck with 52 cards"""
        self.cards = [
            Card(rank, suit)
            for rank in CARD_RANKS
            for suit in CARD_SUITS
        ]
        self.rng.shuffle(self.cards)

    def draw(self) -> Card:
        """Draw a card; reshuffle if empty"""
        if not self.cards:
            self._init_deck()
        return self.cards.pop()

    def draw_n(self, n: int) -> List[Card]:
        """Draw n cards"""
        return [self.draw() for _ in range(n)]


# ============================================================================
# HAND EVALUATION
# ============================================================================

def compute_blackjack_value(cards: List[Card]) -> int:
    """
    Compute the best blackjack value for a hand.
    Aces count as 11 if it doesn't bust, else 1.
    Returns value in range [0, 31] where bust means >21.
    """
    value = 0
    aces = 0

    for card in cards:
        if card.rank == 'A':
            aces += 1
            value += 11
        else:
            value += RANK_VALUES[card.rank]

    # Adjust for aces
    while value > 21 and aces > 0:
        value -= 10  # Convert one ace from 11 to 1
        aces -= 1

    return value


def is_natural_blackjack(cards: List[Card]) -> bool:
    """
    Natural blackjack: exactly 2 cards (one Ace + one 10-value)
    NOT from a split.
    """
    if len(cards) != 2:
        return False

    ranks = {card.rank for card in cards}
    has_ace = 'A' in ranks
    has_ten = any(r in ranks for r in ['10', 'J', 'Q', 'K'])

    return has_ace and has_ten


def get_hand_rank_and_value(cards: List[Card]) -> Tuple[HandRank, int]:
    """
    Evaluate a hand and return (rank, value).
    Value is used for tie-breaking.
    """
    if not cards:
        return (HandRank.BUST, 0)

    value = compute_blackjack_value(cards)

    if value > 21:
        return (HandRank.BUST, 0)

    if value == 21:
        if is_natural_blackjack(cards):
            return (HandRank.NATURAL_BLACKJACK, value)
        else:
            return (HandRank.TWENTY_ONE, value)

    return (HandRank.HIGH_CARD, value)


def compare_natural_blackjacks(cards1: List[Card], cards2: List[Card]) -> int:
    """
    Compare two natural blackjack hands.
    Returns: 1 if cards1 wins, -1 if cards2 wins, 0 if tie.

    Rules:
    1. Compare 10-value rank: K > Q > J > 10
    2. If same, compare suitedness: suited > offsuit
    3. If both offsuit and same rank: tie (split)
    """
    def extract_ten_value(cards):
        """Get the 10-value card from a natural blackjack"""
        for card in cards:
            if card.rank in ['K', 'Q', 'J', '10']:
                return card
        return None

    def suit_value(card):
        return SUIT_RANKS.get(card.suit, 0)

    # Ten-value rank: K=4, Q=3, J=2, 10=1
    TEN_RANK_VALUE = {'K': 4, 'Q': 3, 'J': 2, '10': 1}

    ten1 = extract_ten_value(cards1)
    ten2 = extract_ten_value(cards2)

    val1 = TEN_RANK_VALUE.get(ten1.rank, 0) if ten1 else 0
    val2 = TEN_RANK_VALUE.get(ten2.rank, 0) if ten2 else 0

    if val1 != val2:
        return 1 if val1 > val2 else -1

    # Same ten-value rank; check if suited
    ace1 = next(c for c in cards1 if c.rank == 'A')
    ace2 = next(c for c in cards2 if c.rank == 'A')

    suit1_match = ace1.suit == ten1.suit
    suit2_match = ace2.suit == ten2.suit

    if suit1_match and not suit2_match:
        return 1
    if suit2_match and not suit1_match:
        return -1

    # Both same suitedness = tie
    return 0


SUIT_RANKS = {}  # No suit hierarchy


# ============================================================================
# PLAYER STATE
# ============================================================================

@dataclass
class SplitHand:
    """Represents a split hand (created from original hand)"""
    cards: List[Card] = field(default_factory=list)
    is_from_split: bool = True


@dataclass
class PlayerHand:
    """Represents a player's hand(s) in a round"""
    original_cards: List[Card] = field(default_factory=list)
    revealed_card: Optional[Card] = None  # first revealed card
    cards_drawn: int = 0  # count of cards drawn after initial 2
    is_folded: bool = False
    is_bust: bool = False
    split_hands: List[SplitHand] = field(default_factory=list)
    action_this_phase: Optional[str] = None  # 'hit', 'stand', 'double', 'split'
    escrow_locked: bool = False  # true if chose hit in draw phase


@dataclass
class PlayerState:
    """State of one player at the table"""
    seat: int
    user_id: int
    username: str
    stack: int  # remaining chips
    normal_circle: int = 0  # chips in normal pot
    escrow_circle: int = 0  # chips in escrow pot
    hand: Optional[PlayerHand] = None
    is_dealer: bool = False
    is_button: bool = False
    is_active: bool = True  # whether still in game


# ============================================================================
# GAME STATE
# ============================================================================

@dataclass
class GameState:
    """Complete game state for one hand"""

    # Players
    players: List[PlayerState] = field(default_factory=list)
    button_seat: int = 0

    # Phase management
    phase: GamePhase = GamePhase.SETUP
    current_player_seat: Optional[int] = None
    current_action_step: int = 0  # 0=escrow, 1=normal, or varies by phase

    # Deck
    deck: Optional[Deck] = None

    # Pots
    normal_pot: int = 0
    escrow_pot: int = 0
    current_highest_normal: int = 0  # Highest normal bet this round

    # Action tracking
    action_history: List[Dict] = field(default_factory=list)
    players_acted_this_step: Set[int] = field(default_factory=set)  # seat numbers who acted this step

    # Hand number
    hand_number: int = 1

    def __post_init__(self):
        if not self.deck:
            self.deck = Deck()

    def get_active_players(self) -> List[PlayerState]:
        """Get players still in this hand"""
        return [p for p in self.players if p.is_active and not p.hand.is_folded]

    def get_remaining_players(self) -> List[PlayerState]:
        """Get players who haven't acted this turn"""
        if not self.current_player_seat:
            return []
        # (simplified; full logic would track acted players)
        return self.get_active_players()

    def get_action_order_from_seat(self, start_seat: int) -> List[int]:
        """Get seat order starting from start_seat, clockwise"""
        active_seats = [p.seat for p in self.players if p.is_active]
        if not active_seats:
            return []

        start_idx = active_seats.index(start_seat) if start_seat in active_seats else 0
        return active_seats[start_idx:] + active_seats[:start_idx]


# ============================================================================
# HAND EVALUATION & POT SETTLEMENT
# ============================================================================

def determine_hand_winner(
    hands: Dict[int, List[Card]],
    active_seats: Set[int]
) -> Tuple[int, str]:
    """
    Determine the winner(s) among hands.
    Returns: (winning_seat, "sole" or "tie")
    Assumes all hands are evaluated per blackjack rules.
    """
    best_rank = HandRank.BUST
    best_value = 0
    best_seats = []

    for seat, cards in hands.items():
        if seat not in active_seats:
            continue

        rank, value = get_hand_rank_and_value(cards)

        if rank.value > best_rank.value or (rank == best_rank and value > best_value):
            best_rank = rank
            best_value = value
            best_seats = [seat]
        elif rank == best_rank and value == best_value:
            best_seats.append(seat)

    if not best_seats:
        raise ValueError("No valid hands to determine winner")

    return (best_seats[0], "sole" if len(best_seats) == 1 else "tie")


def settle_pots(
    game_state: GameState,
) -> Dict[int, int]:
    """
    Settle main and escrow pots.
    Returns dict: {seat: total_winnings}
    """
    payouts = defaultdict(int)

    # Collect non-folded hands
    hands: Dict[int, List[Card]] = {}
    active_seats = set()
    for p in game_state.players:
        if p.is_active and p.hand and p.hand.original_cards and not p.hand.is_folded:
            hands[p.seat] = p.hand.original_cards
            active_seats.add(p.seat)

    if not hands:
        # No active players, no payouts
        return dict(payouts)

    # Main pot: best hand wins all normal circle contributions
    winner_seat, _ = determine_hand_winner(hands, active_seats)
    payouts[winner_seat] += game_state.normal_pot

    # Escrow pot: layered distribution based on escrow contributions
    if game_state.escrow_pot > 0:
        # Collect escrow amounts for remaining players
        escrow_amounts = {
            p.seat: p.escrow_circle
            for p in game_state.players
            if p.seat in active_seats
        }

        if escrow_amounts:
            # Sort seats by escrow amount ascending
            sorted_seats = sorted(escrow_amounts.keys(), key=lambda s: escrow_amounts[s])

            # Create layers
            remaining_escrow = game_state.escrow_pot
            remaining_seats = set(sorted_seats)

            for i, min_seat in enumerate(sorted_seats):
                if remaining_escrow <= 0 or not remaining_seats:
                    break

                min_escrow = escrow_amounts[min_seat]
                # Layer size is difference to next level or current escrow if last
                if i < len(sorted_seats) - 1:
                    next_escrow = escrow_amounts[sorted_seats[i + 1]]
                    layer_per_player = next_escrow - min_escrow
                else:
                    # Last layer: all remaining
                    layer_per_player = min_escrow

                # Eligible players for this layer (those with enough escrow)
                eligible = {s for s in remaining_seats if escrow_amounts[s] >= min_escrow}
                if not eligible:
                    break

                # Distribute this layer
                layer_total = min(layer_per_player * len(eligible), remaining_escrow)

                # Find best hand among eligible
                eligible_hands = {s: hands[s] for s in eligible if s in hands}
                if eligible_hands:
                    layer_winner, _ = determine_hand_winner(eligible_hands, eligible)
                    payouts[layer_winner] += layer_total
                    remaining_escrow -= layer_total
                    # Remove seated players from remaining
                    if i < len(sorted_seats) - 1:
                        remaining_seats = {s for s in remaining_seats if escrow_amounts[s] > next_escrow}

    return dict(payouts)


# ============================================================================
# ACTION VALIDATION & EXECUTION
# ============================================================================

def calculate_pot_limit(game_state: GameState) -> int:
    """
    Calculate the maximum bet/raise amount under pot-limit rules.
    Pot Limit: max_raise_to = current_highest_normal + TABLE_TOTAL
    where TABLE_TOTAL = sum(all normal circles) + sum(all escrow circles)
    """
    table_total = game_state.normal_pot + game_state.escrow_pot
    max_bet = game_state.current_highest_normal + table_total
    return max_bet


def can_player_act_now(game_state: GameState, seat: int) -> bool:
    """Check if player at seat can act right now"""
    return game_state.current_player_seat == seat


def get_legal_actions(game_state: GameState, seat: int) -> Dict:
    """Get legal actions for player at seat in current phase. Returns dict with action details and limits."""
    if not can_player_act_now(game_state, seat):
        return {"actions": []}

    player = next((p for p in game_state.players if p.seat == seat), None)
    if not player or player.hand.is_folded or not player.is_active:
        return {"actions": []}

    actions = []
    pot_limit_amount = calculate_pot_limit(game_state)

    if game_state.phase == GamePhase.PREFLOP:
        if game_state.current_action_step == 0:
            # Escrow phase: can add escrow or skip
            actions = [
                {"action": ActionType.ADD_ESCROW.value, "min": 0, "max": min(player.stack, player.stack)}
            ]
        else:
            # Normal betting phase
            max_raise = min(player.stack, pot_limit_amount)
            actions = [
                {"action": ActionType.CHECK.value},
                {"action": ActionType.FOLD.value},
                {"action": ActionType.CALL.value, "amount": game_state.current_highest_normal},
                {"action": ActionType.BET.value, "min": 1, "max": max_raise},
                {"action": ActionType.RAISE.value, "min": game_state.current_highest_normal + 1, "max": max_raise},
            ]

    elif game_state.phase == GamePhase.DRAW:
        # Can hit, stand, double, or split
        actions = [
            {"action": ActionType.HIT.value},
            {"action": ActionType.STAND.value}
        ]
        if player.hand.cards_drawn == 0:  # Only on initial 2 cards
            if len(player.hand.original_cards) == 2 and player.hand.original_cards[0].rank == player.hand.original_cards[1].rank:
                actions.append({"action": ActionType.SPLIT.value})
            actions.append({"action": ActionType.DOUBLE.value})

    elif game_state.phase == GamePhase.RIVER:
        if game_state.current_action_step == 0:
            # Escrow phase: can add escrow (if not escrow-locked from hit)
            if not player.hand.escrow_locked:
                actions = [
                    {"action": ActionType.ADD_ESCROW.value, "min": 0, "max": min(player.stack, player.stack)}
                ]
            # If escrow_locked, player cannot act in escrow step - auto-skip handled in _advance_turn
        else:
            # Normal betting phase
            max_raise = min(player.stack, pot_limit_amount)
            actions = [
                {"action": ActionType.CHECK.value},
                {"action": ActionType.FOLD.value},
                {"action": ActionType.CALL.value, "amount": game_state.current_highest_normal},
                {"action": ActionType.BET.value, "min": 1, "max": max_raise},
                {"action": ActionType.RAISE.value, "min": game_state.current_highest_normal + 1, "max": max_raise},
            ]

    return {
        "actions": actions,
        "current_highest_normal": game_state.current_highest_normal,
        "pot_limit": pot_limit_amount,
        "player_stack": player.stack
    }


# ============================================================================
# GAME ENGINE (Main Logic)
# ============================================================================

class BlackjackGameEngine:
    """Main game engine for Two-Circle Royal 21"""

    def __init__(self, seed: Optional[int] = None):
        self.game_state: Optional[GameState] = None
        self.seed = seed

    def create_table(self, player_list: List[Tuple[int, str]], initial_stack: int = 1000) -> GameState:
        """
        Create a new table.
        player_list: [(user_id, username), ...]
        """
        game_state = GameState(hand_number=1)
        game_state.deck = Deck(seed=self.seed)

        for seat, (user_id, username) in enumerate(player_list):
            player = PlayerState(
                seat=seat,
                user_id=user_id,
                username=username,
                stack=initial_stack
            )
            game_state.players.append(player)

        game_state.button_seat = 0
        game_state.phase = GamePhase.SETUP

        self.game_state = game_state
        return game_state

    def start_hand(self) -> None:
        """Initialize a new hand: antes, deal, set up first-to-act"""
        gs = self.game_state

        # Reset pots and tracking
        gs.normal_pot = 0
        gs.escrow_pot = 0
        gs.current_highest_normal = 0
        gs.players_acted_this_step.clear()
        gs.action_history.clear()

        # Phase 0a: Post antes
        for player in gs.players:
            player.hand = PlayerHand()
            player.is_active = True

            # Escrow ante (all active players)
            if player.stack >= ESCROW_ANTE:
                player.escrow_circle = ESCROW_ANTE
                player.stack -= ESCROW_ANTE
                gs.escrow_pot += ESCROW_ANTE

            # Button posts to normal
            if player.seat == gs.button_seat and player.stack >= BUTTON_ANTE:
                player.normal_circle = BUTTON_ANTE
                player.stack -= BUTTON_ANTE
                gs.normal_pot += BUTTON_ANTE

        # Phase 0b: Deal 2 cards to each
        for player in gs.players:
            player.hand.original_cards = gs.deck.draw_n(2)

        # Update phase and set first-to-act
        gs.phase = GamePhase.PREFLOP
        gs.current_action_step = 0  # Start with escrow step
        first_to_act = (gs.button_seat + 1) % len(gs.players)
        gs.current_player_seat = first_to_act

    def player_action(self, seat: int, action: ActionType, amount: int = 0) -> None:
        """
        Execute a player action with proper state management.
        """
        gs = self.game_state
        player = next((p for p in gs.players if p.seat == seat), None)

        if not player or not can_player_act_now(gs, seat):
            raise ValueError(f"Player {seat} cannot act now")

        if action == ActionType.ADD_ESCROW:
            if gs.current_action_step == 0:  # Escrow step
                # Add to escrow (up to stack, respecting river restrictions)
                # In river escrow step, cannot add escrow if escrow_locked
                if gs.phase == GamePhase.RIVER and player.hand.escrow_locked:
                    raise ValueError("Cannot add escrow - escrow was locked in draw phase")
                add_amount = min(amount, player.stack)
                if add_amount > 0:
                    player.escrow_circle += add_amount
                    player.stack -= add_amount
                    gs.escrow_pot += add_amount
                gs.players_acted_this_step.add(seat)
                self._advance_turn(gs)
            else:
                raise ValueError("Cannot add escrow outside escrow step")

        elif action == ActionType.FOLD:
            player.hand.is_folded = True
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.CHECK:
            # Only valid if current highest is 0
            if gs.current_highest_normal > 0:
                raise ValueError("Cannot check when there's a bet")
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.CALL:
            # Match current highest bet
            call_amount = min(gs.current_highest_normal - player.normal_circle, player.stack)
            if call_amount > 0:
                player.normal_circle += call_amount
                player.stack -= call_amount
                gs.normal_pot += call_amount
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.BET:
            # Place new bet
            pot_limit = calculate_pot_limit(gs)
            bet_amount = min(amount, player.stack, pot_limit)
            if bet_amount <= 0:
                raise ValueError("Bet amount must be positive")
            player.normal_circle += bet_amount
            player.stack -= bet_amount
            gs.normal_pot += bet_amount
            gs.current_highest_normal = max(gs.current_highest_normal, player.normal_circle)
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.RAISE:
            # Raise to specified amount
            pot_limit = calculate_pot_limit(gs)
            raise_to = min(amount, player.stack + player.normal_circle, pot_limit)
            additional = raise_to - player.normal_circle
            if additional <= 0:
                raise ValueError("Raise must be more than current bet")
            player.normal_circle = raise_to
            player.stack -= additional
            gs.normal_pot += additional
            gs.current_highest_normal = raise_to
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.HIT:
            new_card = gs.deck.draw()
            player.hand.original_cards.append(new_card)
            player.hand.cards_drawn += 1
            player.hand.action_this_phase = "hit"
            player.hand.escrow_locked = True  # Lock escrow after hit
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.STAND:
            player.hand.action_this_phase = "stand"
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.DOUBLE:
            if player.hand.cards_drawn > 0:
                raise ValueError("Cannot double after hitting")
            # Player doubles their bet (add equal amount to normal circle)
            double_amount = min(player.normal_circle, player.stack)
            player.normal_circle += double_amount
            player.stack -= double_amount
            gs.normal_pot += double_amount
            # Draw one card and stand
            new_card = gs.deck.draw()
            player.hand.original_cards.append(new_card)
            player.hand.cards_drawn = 1
            player.hand.action_this_phase = "double"
            player.hand.escrow_locked = True  # Escrow locked after double (counts as hitting)
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        elif action == ActionType.SPLIT:
            if len(player.hand.original_cards) != 2:
                raise ValueError("Can only split initial 2 cards")
            if player.hand.original_cards[0].rank != player.hand.original_cards[1].rank:
                raise ValueError("Can only split matching ranks")

            # Create split hands
            split1 = SplitHand(cards=[player.hand.original_cards[0]])
            split2 = SplitHand(cards=[player.hand.original_cards[1]])
            player.hand.split_hands = [split1, split2]
            player.hand.action_this_phase = "split"
            player.hand.escrow_locked = True  # Escrow locked after split
            gs.players_acted_this_step.add(seat)
            self._advance_turn(gs)

        else:
            raise ValueError(f"Unknown action: {action}")

    def _advance_turn(self, gs: GameState) -> None:
        """
        Advance turn within a phase, handling step transitions.
        For PREFLOP/RIVER: each player acts in 2 steps (escrow=0, normal=1)
        For DRAW: players act in sequence without steps
        """
        # Get players who need to act
        active_players = gs.get_action_order_from_seat(gs.current_player_seat)
        non_folded = [p for p in active_players if p < len(gs.players) and not gs.players[p].hand.is_folded]

        if not non_folded:
            return

        # Check if all players have acted in current step
        if all(seat in gs.players_acted_this_step for seat in non_folded):
            # All players acted in this step
            if gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER]:
                if gs.current_action_step == 0:
                    # Transition from escrow step (0) to normal step (1)
                    gs.current_action_step = 1
                    gs.players_acted_this_step.clear()
                    # Reset current player to first-to-act for normal step
                    gs.current_player_seat = (gs.button_seat + 1) % len(gs.players)
                else:
                    # Both steps complete for this round, phase will advance
                    self._phase_complete(gs)
            elif gs.phase == GamePhase.DRAW:
                # DRAW phase: check if all players have acted
                # Use phase_complete_check to transition to river
                self.phase_complete_check()
        else:
            # Move to next player who hasn't acted
            try:
                current_idx = active_players.index(gs.current_player_seat)
                for i in range(1, len(active_players)):
                    next_idx = (current_idx + i) % len(active_players)
                    next_seat = active_players[next_idx]
                    if next_seat not in gs.players_acted_this_step:
                        # Check if this player can act (not escrow-locked in river escrow step)
                        player = gs.players[next_seat]
                        if gs.phase == GamePhase.RIVER and gs.current_action_step == 0 and player.hand.escrow_locked:
                            # Auto-skip this player's escrow turn
                            gs.players_acted_this_step.add(next_seat)
                            # Recursively advance to next player
                            self._advance_turn(gs)
                            return
                        gs.current_player_seat = next_seat
                        return
                # All players have acted - for draw phase, check for completion
                if gs.phase == GamePhase.DRAW:
                    self.phase_complete_check()
            except (ValueError, IndexError):
                gs.current_player_seat = None

    def _phase_complete(self, gs: GameState) -> None:
        """Mark betting round as complete and transition to next phase"""
        # Reset for next phase
        gs.players_acted_this_step.clear()
        gs.current_action_step = 0
        gs.current_highest_normal = 0

        if gs.phase == GamePhase.PREFLOP:
            gs.phase = GamePhase.DRAW
        elif gs.phase == GamePhase.RIVER:
            gs.phase = GamePhase.SHOWDOWN

    def phase_complete_check(self) -> bool:
        """Check if current phase is complete; auto-advance if needed"""
        gs = self.game_state

        if gs.phase == GamePhase.DRAW:
            # Check if all active players have acted in draw phase
            active = gs.get_active_players()
            if not active:
                return False

            if all(p.hand.action_this_phase is not None for p in active if not p.hand.is_folded):
                gs.phase = GamePhase.RIVER
                gs.current_action_step = 0  # Start river with escrow step
                gs.players_acted_this_step.clear()
                gs.current_highest_normal = 0
                gs.current_player_seat = (gs.button_seat + 1) % len(gs.players)
                return True

        elif gs.phase == GamePhase.SHOWDOWN:
            # Execute showdown
            payouts = settle_pots(gs)
            for seat, payout in payouts.items():
                player = next((p for p in gs.players if p.seat == seat), None)
                if player:
                    player.stack += payout

            gs.phase = GamePhase.HAND_OVER
            return True

        return False

    def next_hand(self) -> None:
        """Rotate button and start next hand"""
        gs = self.game_state
        # Rotate button clockwise
        gs.button_seat = (gs.button_seat + 1) % len(gs.players)
        gs.hand_number += 1
        self.start_hand()

    def get_state(self) -> Dict:
        """Export game state as JSON-serializable dict"""
        if not self.game_state:
            return {}

        gs = self.game_state

        return {
            "hand_number": gs.hand_number,
            "phase": gs.phase.value,
            "button_seat": gs.button_seat,
            "current_player_seat": gs.current_player_seat,
            "current_action_step": gs.current_action_step,  # 0=escrow, 1=normal
            "normal_pot": gs.normal_pot,
            "escrow_pot": gs.escrow_pot,
            "current_highest_normal": gs.current_highest_normal,
            "players": [
                {
                    "seat": p.seat,
                    "user_id": p.user_id,
                    "username": p.username,
                    "stack": p.stack,
                    "normal_circle": p.normal_circle,
                    "escrow_circle": p.escrow_circle,
                    "is_active": p.is_active,
                    "is_button": p.seat == gs.button_seat,
                    "is_folded": p.hand.is_folded if p.hand else False,
                    "escrow_locked": p.hand.escrow_locked if p.hand else False,
                    "cards": [str(c) for c in (p.hand.original_cards if p.hand else [])],
                    "cards_count": len(p.hand.original_cards) if p.hand else 0,
                    "cards_drawn": p.hand.cards_drawn if p.hand else 0,
                    "action_this_phase": p.hand.action_this_phase if p.hand else None,
                }
                for p in gs.players
            ],
            "action_history": gs.action_history,
        }
