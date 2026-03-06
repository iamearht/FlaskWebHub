"""
Core game engine for Royal 21 card game.
Implements all game rules with proper state management and hidden information protection.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict, Tuple
from collections import defaultdict
import random
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# ENUMS
# ============================================================================

class GamePhase(Enum):
    SETUP = "setup"
    PREFLOP = "preflop"
    DRAW = "draw"
    RIVER = "river"
    SHOWDOWN = "showdown"
    HAND_END = "hand_end"

class ActionType(Enum):
    ADD_ESCROW = "add_escrow"
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    EXPOSE_CARD = "expose_card"

# ============================================================================
# CONSTANTS
# ============================================================================

MAX_PLAYERS = 5
MIN_PLAYERS = 2
ESCROW_ANTE = 1
BUTTON_ANTE = 1

CARD_RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
CARD_SUITS = ['♠', '♥', '♦', '♣']
RANK_VALUES = {
    'A': 11, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '10': 10, 'J': 10, 'Q': 10, 'K': 10
}

# ============================================================================
# CARD & DECK
# ============================================================================

@dataclass(frozen=True)
class Card:
    """Immutable playing card"""
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return str(self)


class Deck:
    """Standard 52-card deck with shuffle"""

    def __init__(self, seed: Optional[int] = None):
        self.cards: List[Card] = []
        self.rng = random.Random(seed)
        self._init_deck()

    def _init_deck(self):
        self.cards = [
            Card(rank, suit)
            for rank in CARD_RANKS
            for suit in CARD_SUITS
        ]
        self.rng.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            self._init_deck()
        return self.cards.pop()

    def draw_n(self, n: int) -> List[Card]:
        return [self.draw() for _ in range(n)]


# ============================================================================
# HAND EVALUATION
# ============================================================================

def compute_hand_value(cards: List[Card]) -> int:
    """Compute blackjack hand value. Aces adjust from 11 to 1 to avoid bust."""
    value = 0
    aces = 0

    for card in cards:
        if card.rank == 'A':
            aces += 1
            value += 11
        else:
            value += RANK_VALUES[card.rank]

    # Adjust aces from 11 to 1
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1

    return value


def is_natural_blackjack(cards: List[Card]) -> bool:
    """Natural blackjack: exactly 2 original cards, one Ace + one 10-value."""
    if len(cards) != 2:
        return False
    ranks = {card.rank for card in cards}
    has_ace = 'A' in ranks
    has_ten = any(r in ranks for r in ['10', 'J', 'Q', 'K'])
    return has_ace and has_ten


@dataclass
class HandValue:
    """Evaluated hand with ranking"""
    is_blackjack: bool
    is_bust: bool
    value: int
    cards: List[Card]

    @staticmethod
    def evaluate(cards: List[Card]) -> 'HandValue':
        if not cards:
            return HandValue(False, True, 0, cards)

        value = compute_hand_value(cards)
        is_bust = value > 21
        is_blackjack = is_natural_blackjack(cards) if not is_bust else False

        return HandValue(is_blackjack, is_bust, value, cards)

    def rank_order(self) -> Tuple[int, int, int]:
        """Return tuple for ranking: (is_blackjack, non_bust, value)."""
        if self.is_bust:
            return (0, 0, 0)  # Worst
        if self.is_blackjack:
            return (2, 1, self.value)  # Best
        return (1, 1, self.value)  # Middle


def compare_blackjacks(hand1: List[Card], hand2: List[Card]) -> int:
    """
    Compare natural blackjacks.
    Returns: 1 if hand1 wins, -1 if hand2 wins, 0 if tie.

    AK > AQ > AJ > A10
    Then suited > offsuit
    Then tie
    """
    if not (is_natural_blackjack(hand1) and is_natural_blackjack(hand2)):
        return 0

    def get_ten_and_ace(cards):
        ten = next((c for c in cards if c.rank in ['K', 'Q', 'J', '10']), None)
        ace = next((c for c in cards if c.rank == 'A'), None)
        return ten, ace

    ten1, ace1 = get_ten_and_ace(hand1)
    ten2, ace2 = get_ten_and_ace(hand2)

    # Rank ten values: K=4, Q=3, J=2, 10=1
    ten_ranks = {'K': 4, 'Q': 3, 'J': 2, '10': 1}
    rank1 = ten_ranks.get(ten1.rank, 0) if ten1 else 0
    rank2 = ten_ranks.get(ten2.rank, 0) if ten2 else 0

    if rank1 != rank2:
        return 1 if rank1 > rank2 else -1

    # Same rank, check suitedness
    suited1 = ace1.suit == ten1.suit
    suited2 = ace2.suit == ten2.suit

    if suited1 and not suited2:
        return 1
    if suited2 and not suited1:
        return -1

    return 0  # Tie


# ============================================================================
# PLAYER STATE
# ============================================================================

@dataclass
class SplitHand:
    """A split hand (second hand from splitting)"""
    cards: List[Card] = field(default_factory=list)
    hand_values: Optional[HandValue] = None

    def evaluate(self) -> HandValue:
        self.hand_values = HandValue.evaluate(self.cards)
        return self.hand_values


@dataclass
class PlayerHand:
    """Represents a player's hand(s) in one round"""
    original_cards: List[Card] = field(default_factory=list)
    split_hands: List[SplitHand] = field(default_factory=list)

    # Action tracking
    folded: bool = False
    escrow_locked: bool = False
    action_this_phase: Optional[str] = None
    exposed_card: Optional[Card] = None
    first_action_taken: bool = False

    # Draw phase tracking
    cards_drawn: int = 0

    def evaluate_main(self) -> HandValue:
        return HandValue.evaluate(self.original_cards)

    def all_hands(self) -> List[HandValue]:
        """Return all hand values (main + splits)"""
        if not self.split_hands:
            return [self.evaluate_main()]

        result = [self.evaluate_main()]
        for split in self.split_hands:
            result.append(split.evaluate())
        return result


@dataclass
class PlayerState:
    """Complete player state"""
    seat: int
    player_id: str
    username: str
    stack: int

    # Circles
    normal_circle: int = 0
    escrow_circle: int = 0

    # Hand state
    hand: Optional[PlayerHand] = None
    is_active: bool = True

    # Button/dealer state
    is_button: bool = False


# ============================================================================
# GAME STATE
# ============================================================================

@dataclass
class GameState:
    """Complete game state for one hand"""
    players: List[PlayerState] = field(default_factory=list)
    button_seat: int = 0

    # Phase management
    phase: GamePhase = GamePhase.SETUP
    current_player_seat: Optional[int] = None
    current_action_step: int = 0  # 0=escrow, 1=normal

    # Deck
    deck: Optional[Deck] = None

    # Pots
    normal_pot: int = 0
    escrow_pot: int = 0
    current_highest_normal: int = 0

    # Action tracking
    players_acted_this_step: Set[int] = field(default_factory=set)
    action_history: List[Dict] = field(default_factory=list)
    last_raiser_seat: Optional[int] = None  # Track last raise/bet for betting round end condition

    # Hand tracking
    hand_number: int = 1

    # Table initialization tracking
    table_initialized: bool = False  # True after first hand's button is determined

    # Table configuration
    ante_value: int = 1  # Chips per ante (e.g., 10)

    def __post_init__(self):
        if not self.deck:
            self.deck = Deck()

    def get_active_players(self) -> List[PlayerState]:
        """Get non-folded players"""
        return [
            p for p in self.players
            if p.is_active and p.hand and not p.hand.folded
        ]

    def get_action_order_from_seat(self, start_seat: int) -> List[int]:
        """Get action order starting from seat, clockwise"""
        active_seats = [
            p.seat for p in self.players
            if p.is_active
        ]
        if not active_seats:
            return []

        start_idx = active_seats.index(start_seat) if start_seat in active_seats else 0
        return active_seats[start_idx:] + active_seats[:start_idx]


# ============================================================================
# GAME ENGINE
# ============================================================================

class GameEngine:
    """Core game engine"""

    def __init__(self, seed: Optional[int] = None, ante_value: int = 1):
        self.game_state: Optional[GameState] = None
        self.seed = seed
        self.ante_value = ante_value  # Chips per ante (e.g., 10)

    def create_table(
        self,
        player_list: List[Tuple[int, str, str]],  # [(seat_number, player_id, username), ...]
        initial_stack: int = 1000,
        ante_value: int = 1
    ) -> GameState:
        """Create new table and initialize game state"""
        if len(player_list) > MAX_PLAYERS:
            raise ValueError(f"Max {MAX_PLAYERS} players allowed")
        if len(player_list) < MIN_PLAYERS:
            raise ValueError(f"Min {MIN_PLAYERS} players required")

        # Store ante_value for later use
        self.ante_value = ante_value

        game_state = GameState(hand_number=1)
        game_state.deck = Deck(seed=self.seed)
        game_state.ante_value = ante_value  # Store in game state for reference

        for seat_number, player_id, username in player_list:
            player = PlayerState(
                seat=seat_number,
                player_id=player_id,
                username=username,
                stack=initial_stack
            )
            game_state.players.append(player)

        game_state.button_seat = 0
        game_state.phase = GamePhase.SETUP

        self.game_state = game_state
        return game_state

    def setup_hand(self) -> None:
        """Initialize new hand: post antes, determine button, deal 2 face-down cards, transition to PREFLOP"""
        gs = self.game_state
        assert gs is not None

        # Reset state for new hand
        gs.normal_pot = 0
        gs.escrow_pot = 0
        gs.current_highest_normal = 0
        gs.players_acted_this_step.clear()
        gs.action_history.clear()

        # Initialize hands and post escrow antes
        for player in gs.players:
            player.hand = PlayerHand()
            player.is_active = True

            # Everyone antes 1 escrow (scaled by ante_value)
            escrow_chips = ESCROW_ANTE * self.ante_value
            if player.stack >= escrow_chips:
                player.escrow_circle = escrow_chips  # Track in chips, not antes
                player.stack -= escrow_chips
                gs.escrow_pot += escrow_chips

            # Initialize button status and normal circle
            player.is_button = False
            player.normal_circle = 0

        # Determine button via card draw (first hand only)
        if not gs.table_initialized:
            self._determine_button()
            gs.table_initialized = True
        else:
            # On subsequent hands, just rotate button one position left
            gs.button_seat = (gs.button_seat + 1) % len(gs.players)

        # Reset button's escrow_circle to 0 (button only posts normal ante, not escrow ante)
        # This prevents button from being incorrectly skipped in escrow step
        if gs.button_seat < len(gs.players):
            gs.players[gs.button_seat].escrow_circle = 0

        # DEBUG: Log player states after initialization
        logger.info(f"=== SETUP_HAND: Player states after button reset ===")
        for i, player in enumerate(gs.players):
            logger.info(f"Player {i} (seat {player.seat}): normal={player.normal_circle}, escrow={player.escrow_circle}, is_button={player.is_button}")

        # Deal 2 face-down cards to each player
        for player in gs.players:
            cards = gs.deck.draw_n(2)
            player.hand.original_cards = cards

        # Transition to PREFLOP phase
        gs.phase = GamePhase.PREFLOP
        gs.current_action_step = 0  # Escrow step
        gs.current_player_seat = (gs.button_seat + 1) % len(gs.players)  # Left of button
        gs.players_acted_this_step.clear()
        # Initialize current_highest_normal to button's ante (button has already posted)
        gs.current_highest_normal = gs.players[gs.button_seat].normal_circle
        gs.last_raiser_seat = gs.button_seat  # Button is the "raiser" that started action

        # Initialize betting action: auto-skip players who don't need to act
        self._handle_initial_skips()

    def _determine_button(self) -> None:
        """Determine button by highest card draw. Handles tiebreakers. Posts button ante."""
        gs = self.game_state
        assert gs is not None

        # Initialize draw_cards for each player
        for player in gs.players:
            player.hand.draw_cards = []

        # Deal 1 face-up card to each player for button determination
        for player in gs.players:
            card = gs.deck.draw()
            player.hand.draw_cards.append(card)

        # Find highest card, handling ties
        button_seat = self._find_highest_card_holder()

        # Find button player by seat number
        button_index = next(
            (idx for idx, p in enumerate(gs.players) if p.seat == button_seat),
            None
        )

        if button_index is not None:
            gs.button_seat = button_index
            button_player = gs.players[button_index]

            # Button antes 1 chip to normal pot (scaled by ante_value)
            button_chips = BUTTON_ANTE * self.ante_value
            if button_player.stack >= button_chips:
                button_player.normal_circle = button_chips  # Track in chips, not antes
                button_player.stack -= button_chips
                gs.normal_pot += button_chips

            # Set button flag
            button_player.is_button = True
            for p in gs.players:
                if p != button_player:
                    p.is_button = False

        # Clear button determination cards (they are discarded)
        for player in gs.players:
            player.hand.draw_cards = []

    def _find_highest_card_holder(self) -> int:
        """Find the player seat with the highest card. Handles ties by drawing additional cards."""
        gs = self.game_state
        assert gs is not None

        tied_players = list(range(len(gs.players)))

        while len(tied_players) > 1:
            # Get the latest card for each tied player
            highest_value = -1
            new_tied = []

            for player_idx in tied_players:
                player = gs.players[player_idx]
                if player.hand.draw_cards:
                    card = player.hand.draw_cards[-1]
                    value = RANK_VALUES.get(card.rank, 0)

                    if value > highest_value:
                        highest_value = value
                        new_tied = [player_idx]
                    elif value == highest_value:
                        new_tied.append(player_idx)

            tied_players = new_tied

            # If still tied, deal another card to tied players
            if len(tied_players) > 1:
                for player_idx in tied_players:
                    player = gs.players[player_idx]
                    card = gs.deck.draw()
                    player.hand.draw_cards.append(card)

        # Return the seat number of the winning player
        if tied_players:
            return gs.players[tied_players[0]].seat
        return 0

    def _handle_initial_skips(self) -> None:
        """Auto-skip players who don't need to act in current step"""
        gs = self.game_state
        assert gs is not None

        # In escrow step, check if current player should skip
        if gs.current_action_step == 0 and gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER]:
            current_player = gs.players[gs.current_player_seat]
            logger.info(f"_handle_initial_skips: phase={gs.phase.value}, step={gs.current_action_step}, current_player_seat={gs.current_player_seat}, player_seat={current_player.seat}, normal={current_player.normal_circle}, escrow={current_player.escrow_circle}")
            if self.should_skip_escrow_step(current_player):
                logger.info(f"  -> Skipping player seat {current_player.seat}, advancing turn")
                # Mark them as acted and advance
                gs.players_acted_this_step.add(gs.current_player_seat)
                self._advance_turn()
            else:
                logger.info(f"  -> Player seat {current_player.seat} should ACT")
        else:
            logger.info(f"_handle_initial_skips: Not escrow step (phase={gs.phase.value if gs else 'None'}, step={gs.current_action_step if gs else 'None'})")

    def should_skip_escrow_step(self, player: PlayerState) -> bool:
        """Check if player should skip escrow step"""
        if not player.hand:
            return False

        # Skip if circles already equal
        if player.normal_circle == player.escrow_circle:
            logger.info(f"  should_skip_escrow_step: circles equal ({player.normal_circle} == {player.escrow_circle}) -> SKIP")
            return True

        # Skip if normal < escrow
        if player.normal_circle < player.escrow_circle:
            logger.info(f"  should_skip_escrow_step: normal < escrow ({player.normal_circle} < {player.escrow_circle}) -> SKIP")
            return True

        # Skip if river and escrow locked
        if (self.game_state.phase == GamePhase.RIVER and
            player.hand.escrow_locked):
            logger.info(f"  should_skip_escrow_step: river and escrow_locked -> SKIP")
            return True

        logger.info(f"  should_skip_escrow_step: no skip conditions met (normal={player.normal_circle}, escrow={player.escrow_circle}) -> ACT")
        return False

    def get_legal_actions(self, seat: int) -> List[ActionType]:
        """Get legal actions for player"""
        gs = self.game_state
        if gs.current_player_seat != seat:
            return []

        player = next((p for p in gs.players if p.seat == seat), None)
        if not player or not player.hand or player.hand.folded:
            return []

        # PREFLOP or RIVER escrow step
        if gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER] and gs.current_action_step == 0:
            if self.should_skip_escrow_step(player):
                # Will auto-skip, no action needed
                return []
            return [ActionType.ADD_ESCROW]

        # PREFLOP or RIVER normal betting step
        if gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER] and gs.current_action_step == 1:
            actions = [ActionType.FOLD]

            # Compute to_call for this player
            to_call = gs.current_highest_normal - player.normal_circle

            # Check availability
            if to_call == 0:
                # Player has matched the current highest
                # Cannot check on first action if not button (special opening situation)
                is_button = (gs.button_seat < len(gs.players) and gs.players[gs.button_seat] == player)
                if is_button or player.hand.first_action_taken:
                    actions.append(ActionType.CHECK)
                actions.append(ActionType.BET)
            else:
                # Player is facing a bet
                actions.append(ActionType.CALL)
                actions.append(ActionType.BET)

            # Can raise if facing a bet or starting a new betting level
            if to_call > 0 or gs.current_highest_normal > 0:
                actions.append(ActionType.RAISE)

            return actions

        # DRAW phase
        if gs.phase == GamePhase.DRAW:
            actions = [ActionType.HIT, ActionType.STAND]

            if player.hand.cards_drawn == 0:
                # Can only double/split on original 2 cards
                if len(player.hand.original_cards) == 2:
                    if player.hand.original_cards[0].rank == player.hand.original_cards[1].rank:
                        actions.append(ActionType.SPLIT)
                    actions.append(ActionType.DOUBLE)

            return actions

        return []

    def player_action(self, seat: int, action: ActionType, amount: int = 0, card_index: Optional[int] = None) -> None:
        """Execute player action"""
        gs = self.game_state
        assert gs is not None

        player = next((p for p in gs.players if p.seat == seat), None)
        if not player or not player.hand or gs.current_player_seat != seat:
            raise ValueError(f"Invalid action for seat {seat}")

        # Check if player must expose a card on first action in PREFLOP normal betting step
        if (gs.phase == GamePhase.PREFLOP and
            gs.current_action_step == 1 and
            not player.hand.first_action_taken):
            if card_index is None:
                raise ValueError("Card exposure required on first action: provide card_index (0 or 1)")
            if card_index not in [0, 1]:
                raise ValueError("card_index must be 0 or 1")
            # Expose the chosen card
            self.expose_card(seat, card_index)
            player.hand.first_action_taken = True

        # ADD_ESCROW
        if action == ActionType.ADD_ESCROW:
            if gs.current_action_step != 0:
                raise ValueError("Cannot add escrow outside escrow step")

            add_amount = min(amount, player.stack)
            # Constraint: new_escrow_circle must not exceed normal_circle
            if player.escrow_circle + add_amount > player.normal_circle:
                raise ValueError("Escrow cannot exceed normal circle")

            player.escrow_circle += add_amount
            player.stack -= add_amount
            gs.escrow_pot += add_amount
            gs.players_acted_this_step.add(seat)

        # FOLD
        elif action == ActionType.FOLD:
            player.hand.folded = True
            gs.players_acted_this_step.add(seat)

        # CHECK
        elif action == ActionType.CHECK:
            if gs.current_highest_normal > 0:
                raise ValueError("Cannot check when facing a bet")
            gs.players_acted_this_step.add(seat)

        # CALL
        elif action == ActionType.CALL:
            call_amount = min(
                gs.current_highest_normal - player.normal_circle,
                player.stack
            )
            if call_amount > 0:
                player.normal_circle += call_amount
                player.stack -= call_amount
                gs.normal_pot += call_amount
            gs.players_acted_this_step.add(seat)

        # BET
        elif action == ActionType.BET:
            table_total = gs.normal_pot + gs.escrow_pot
            max_bet = table_total

            bet_amount = min(amount, player.stack, max_bet)
            if bet_amount <= 0:
                raise ValueError("Bet must be positive")

            if player.normal_circle + bet_amount < player.escrow_circle:
                raise ValueError("Would violate escrow <= normal")

            player.normal_circle += bet_amount
            player.stack -= bet_amount
            gs.normal_pot += bet_amount
            gs.current_highest_normal = max(gs.current_highest_normal, player.normal_circle)
            gs.last_raiser_seat = seat  # Track this bet for end-of-round detection
            gs.players_acted_this_step.add(seat)

        # RAISE
        elif action == ActionType.RAISE:
            table_total = gs.normal_pot + gs.escrow_pot
            max_raise_to = gs.current_highest_normal + table_total

            raise_to = min(amount, player.stack + player.normal_circle, max_raise_to)
            additional = raise_to - player.normal_circle

            if additional <= 0:
                raise ValueError("Raise must increase bet")

            if raise_to < player.escrow_circle:
                raise ValueError("Would violate escrow <= normal")

            player.normal_circle = raise_to
            player.stack -= additional
            gs.normal_pot += additional
            gs.current_highest_normal = raise_to
            gs.last_raiser_seat = seat  # Track this raise for end-of-round detection
            gs.players_acted_this_step.add(seat)

        # HIT
        elif action == ActionType.HIT:
            if gs.phase != GamePhase.DRAW:
                raise ValueError("Can only hit during draw phase")

            new_card = gs.deck.draw()
            player.hand.original_cards.append(new_card)
            player.hand.cards_drawn += 1
            player.hand.escrow_locked = True
            player.hand.action_this_phase = "hit"
            gs.players_acted_this_step.add(seat)

        # STAND
        elif action == ActionType.STAND:
            if gs.phase != GamePhase.DRAW:
                raise ValueError("Can only stand during draw phase")

            player.hand.action_this_phase = "stand"
            gs.players_acted_this_step.add(seat)

        # DOUBLE
        elif action == ActionType.DOUBLE:
            if gs.phase != GamePhase.DRAW:
                raise ValueError("Can only double during draw phase")
            if player.hand.cards_drawn > 0:
                raise ValueError("Cannot double after hitting")

            double_amount = min(player.normal_circle, player.stack)
            player.normal_circle += double_amount
            player.stack -= double_amount
            gs.normal_pot += double_amount

            new_card = gs.deck.draw()
            player.hand.original_cards.append(new_card)
            player.hand.cards_drawn = 1
            player.hand.escrow_locked = True
            player.hand.action_this_phase = "double"
            gs.players_acted_this_step.add(seat)

        # SPLIT
        elif action == ActionType.SPLIT:
            if gs.phase != GamePhase.DRAW:
                raise ValueError("Can only split during draw phase")
            if len(player.hand.original_cards) != 2:
                raise ValueError("Can only split original 2 cards")
            if player.hand.original_cards[0].rank != player.hand.original_cards[1].rank:
                raise ValueError("Can only split matching ranks")

            split1 = SplitHand(cards=[player.hand.original_cards[0]])
            split2 = SplitHand(cards=[player.hand.original_cards[1]])
            player.hand.split_hands = [split1, split2]
            player.hand.action_this_phase = "split"
            player.hand.escrow_locked = True
            gs.players_acted_this_step.add(seat)

        self._advance_turn()

    def expose_card(self, seat: int, card_index: int) -> None:
        """Player exposes one of their two hole cards"""
        gs = self.game_state
        assert gs is not None

        player = next((p for p in gs.players if p.seat == seat), None)
        if not player or not player.hand:
            raise ValueError(f"Invalid seat {seat}")

        if card_index not in [0, 1]:
            raise ValueError("Card index must be 0 or 1")

        if len(player.hand.original_cards) < 2:
            raise ValueError("Player does not have 2 cards")

        player.hand.exposed_card = player.hand.original_cards[card_index]

    def _advance_turn(self) -> None:
        """Advance to next player/step"""
        gs = self.game_state
        assert gs is not None

        logger.info(f"_advance_turn: phase={gs.phase.value}, step={gs.current_action_step}, current_player={gs.current_player_seat}, acted={gs.players_acted_this_step}")

        active_players = gs.get_action_order_from_seat(gs.current_player_seat or 0)
        if not active_players:
            return

        non_folded = [
            p for p in active_players
            if p < len(gs.players) and not gs.players[p].hand.folded
        ]
        logger.info(f"  active_players={active_players}, non_folded={non_folded}")

        # Check if betting round ends
        if gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER] and gs.current_action_step == 1:
            # Betting round ends when:
            # 1. Only one active player remains, or
            # 2. All active players have matched the highest normal AND action has cycled back after last raiser
            if len(non_folded) <= 1:
                # Only one player left - they win the hand
                self._handle_sole_remaining_player()
                return

            # Check if all non-folded players have matched the highest
            all_matched = all(
                gs.players[seat].normal_circle == gs.current_highest_normal
                for seat in non_folded
            )

            if all_matched and gs.last_raiser_seat is not None:
                # Check if action has cycled back to the seat after the last raiser
                active_seats = gs.get_action_order_from_seat(gs.button_seat or 0)
                non_folded_seats = [s for s in active_seats if s in non_folded]

                if non_folded_seats and gs.current_player_seat is not None:
                    try:
                        last_raiser_idx = non_folded_seats.index(gs.last_raiser_seat)
                        next_seat_after_raiser = non_folded_seats[(last_raiser_idx + 1) % len(non_folded_seats)]

                        # If we've cycled back to seat after last raiser, round ends
                        if gs.current_player_seat == next_seat_after_raiser:
                            self._advance_phase()
                            return
                    except ValueError:
                        pass

        # Check if all players in step have acted (for escrow step or draw phase)
        if all(seat in gs.players_acted_this_step for seat in non_folded):
            if gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER]:
                if gs.current_action_step == 0:
                    # Transition from escrow to normal
                    gs.current_action_step = 1
                    gs.players_acted_this_step.clear()
                    gs.current_player_seat = (gs.button_seat + 1) % len(gs.players)
                    gs.last_raiser_seat = gs.button_seat  # Reset raiser tracking for normal betting step
                    # Initialize normal betting action: auto-skip any players who don't need to act
                    self._handle_initial_skips()
                else:
                    # Both steps done, move to next phase
                    self._advance_phase()
            elif gs.phase == GamePhase.DRAW:
                self._check_draw_complete()
        else:
            # Move to next player
            try:
                current_idx = active_players.index(gs.current_player_seat or 0)
                for i in range(1, len(active_players)):
                    next_idx = (current_idx + i) % len(active_players)
                    next_seat = active_players[next_idx]

                    if next_seat not in gs.players_acted_this_step:
                        # Check if should skip escrow step
                        next_player = gs.players[next_seat]
                        if (gs.phase in [GamePhase.PREFLOP, GamePhase.RIVER] and
                            gs.current_action_step == 0 and
                            self.should_skip_escrow_step(next_player)):
                            # Auto-skip this player
                            gs.players_acted_this_step.add(next_seat)
                            # Recursively advance
                            self._advance_turn()
                            return

                        gs.current_player_seat = next_seat
                        return

                # All players acted
                if gs.phase == GamePhase.DRAW:
                    self._check_draw_complete()
            except (ValueError, IndexError):
                gs.current_player_seat = None

    def _handle_sole_remaining_player(self) -> None:
        """Handle case where only one player remains after others fold"""
        gs = self.game_state
        assert gs is not None

        non_folded = [
            p for p in gs.players
            if p.is_active and p.hand and not p.hand.folded
        ]

        if len(non_folded) == 1:
            # One player wins the hand
            winner = non_folded[0]
            winner.stack += gs.normal_pot + gs.escrow_pot

            # Move to showdown to complete hand
            gs.phase = GamePhase.SHOWDOWN
            gs.current_action_step = 0
            gs.players_acted_this_step.clear()
            gs.current_player_seat = None

    def _advance_phase(self) -> None:
        """Move to next phase"""
        gs = self.game_state
        assert gs is not None

        if gs.phase == GamePhase.PREFLOP:
            # First hand: show DRAW phase for button determination animation
            # Subsequent hands: skip DRAW and go straight to RIVER
            if not gs.table_initialized or gs.hand_number == 1:
                gs.phase = GamePhase.DRAW
                # Initialize DRAW phase button determination progression
                gs.draw_phase_step = 0
                gs.draw_phase_timestamp = None
                # Initialize draw_cards for each player
                for player in gs.players:
                    player.hand.draw_cards = []
                # Deal 1 face-up card to each player for button determination
                for player in gs.players:
                    card = gs.deck.draw()
                    player.hand.draw_cards.append(card)
            else:
                gs.phase = GamePhase.RIVER
                gs.current_highest_normal = 0
            gs.current_action_step = 0
            gs.players_acted_this_step.clear()
            gs.current_player_seat = (gs.button_seat + 1) % len(gs.players)

        elif gs.phase == GamePhase.DRAW:
            gs.phase = GamePhase.RIVER
            gs.current_action_step = 0
            gs.players_acted_this_step.clear()
            gs.current_highest_normal = 0
            gs.current_player_seat = (gs.button_seat + 1) % len(gs.players)

        elif gs.phase == GamePhase.RIVER:
            gs.phase = GamePhase.SHOWDOWN

    def _check_draw_complete(self) -> None:
        """Check if draw phase is complete"""
        gs = self.game_state
        assert gs is not None

        active = gs.get_active_players()
        if all(p.hand.action_this_phase for p in active if not p.hand.folded):
            self._advance_phase()

    def progress_button_determination_draw(self) -> None:
        """Automatically progress through DRAW phase for button determination"""
        import time
        gs = self.game_state
        assert gs is not None

        if gs.phase != GamePhase.DRAW or not hasattr(gs, 'draw_phase_step'):
            return

        current_time = time.time()

        # Step 0: Initial 1 card dealt (cards already dealt in setup_hand)
        if gs.draw_phase_step == 0:
            # First time in this step, initialize timestamp
            if gs.draw_phase_timestamp is None:
                gs.draw_phase_timestamp = current_time
            # Wait 3 seconds before determining button
            elif current_time - gs.draw_phase_timestamp >= 3:
                gs.draw_phase_step = 1
                gs.draw_phase_timestamp = None

        # Step 1: Determine button from highest card
        elif gs.draw_phase_step == 1:
            gs.draw_phase_step = 1  # Already set
            if gs.draw_phase_timestamp is None:
                gs.draw_phase_timestamp = current_time

            # Ensure ALL players have draw_cards (handle initialization failures)
            print(f"DEBUG: Step 1 - {len(gs.players)} players")
            for player in gs.players:
                has_cards = hasattr(player.hand, 'draw_cards') and player.hand.draw_cards
                print(f"DEBUG: Seat {player.seat} has draw_cards: {has_cards}, cards: {player.hand.draw_cards if hasattr(player.hand, 'draw_cards') else 'NO ATTR'}")
                if not hasattr(player.hand, 'draw_cards') or not player.hand.draw_cards:
                    # If player somehow doesn't have a draw card, give them one now
                    player.hand.draw_cards = gs.deck.draw_n(1)
                    print(f"DEBUG: Had to redraw for seat {player.seat}: {player.hand.draw_cards}")

            # Find highest card value(s) - check ALL players
            highest_value = 0
            tied_players = []

            for player in gs.players:
                if player.hand.draw_cards and len(player.hand.draw_cards) > 0:
                    # Get the LATEST card (for tiebreaker rounds, it's the newest)
                    card = player.hand.draw_cards[-1]
                    value = RANK_VALUES.get(card.rank, 0)
                    print(f"DEBUG: Seat {player.seat} card {card} value {value}")
                    if value > highest_value:
                        highest_value = value
                        tied_players = [player.seat]
                    elif value == highest_value:
                        tied_players.append(player.seat)

            # Handle ties - draw more cards
            if len(tied_players) > 1:
                # Deal another card to tied players
                for seat in tied_players:
                    player = gs.players[seat]
                    new_card = gs.deck.draw()  # Fixed: draw() takes no arguments
                    if not hasattr(player.hand, 'draw_cards'):
                        player.hand.draw_cards = []
                    player.hand.draw_cards.append(new_card)

                # Recurse to check again
                tied_players_new = []
                highest_value_new = 0
                for seat in tied_players:
                    player = gs.players[seat]
                    # Get latest card
                    latest_card = player.hand.draw_cards[-1]
                    value = RANK_VALUES.get(latest_card.rank, 0)
                    if value > highest_value_new:
                        highest_value_new = value
                        tied_players_new = [seat]
                    elif value == highest_value_new:
                        tied_players_new.append(seat)

                tied_players = tied_players_new

            # If still tied, keep drawing (continue this step)
            if len(tied_players) > 1:
                # Will recurse on next call
                return

            # Single winner - they become the button
            if tied_players:
                # tied_players contains seat numbers, find the player by seat number
                button_seat_number = tied_players[0]
                button_player = None

                # Search through all players to find the one with the button seat number
                for p in gs.players:
                    if p.seat == button_seat_number:
                        button_player = p
                        break

                # Set button and apply ante
                if button_player:
                    # Find the player's index for button_seat
                    button_index = next((idx for idx, p in enumerate(gs.players) if p.seat == button_seat_number), None)
                    logger.warning(f"Button determination: button_seat_number={button_seat_number}, button_index={button_index}, total_players={len(gs.players)}")

                    if button_index is not None:
                        gs.button_seat = button_index
                        button_player = gs.players[button_index]  # Get player by index for reliability

                        # Button antes 1 chip to normal pot (scaled by ante_value)
                        button_chips = BUTTON_ANTE * gs.ante_value
                        logger.warning(f"ANTE CHECK: player_id={id(button_player)}, seat={button_player.seat}, stack={button_player.stack}, ante={BUTTON_ANTE}, ante_value={gs.ante_value}, button_chips={button_chips}")

                        if button_player.stack >= button_chips:
                            button_player.normal_circle = BUTTON_ANTE
                            button_player.stack -= button_chips
                            gs.normal_pot += button_chips
                            logger.warning(f"ANTE APPLIED: player_id={id(button_player)}, stack_after={button_player.stack}, normal_pot={gs.normal_pot}, gs.players[button_index].stack={gs.players[button_index].stack}")
                        else:
                            logger.warning(f"ANTE SKIPPED: stack {button_player.stack} < button_chips {button_chips}")

                        # Update is_button flag for all players
                        button_player.is_button = True
                        for p in gs.players:
                            if p != button_player:
                                p.is_button = False

                # Always advance to step 2 after determining button
                gs.draw_phase_step = 2
                gs.draw_phase_timestamp = None

        # Step 2: Wait 3 seconds then deal 2 face-down cards
        elif gs.draw_phase_step == 2:
            if gs.draw_phase_timestamp is None:
                gs.draw_phase_timestamp = current_time
            # Wait 3 seconds then deal
            elif current_time - gs.draw_phase_timestamp >= 3:
                # Deal 2 cards face-down to EACH player
                for player in gs.players:
                    cards = gs.deck.draw_n(2)
                    player.hand.original_cards = cards

                # Verify all players got cards (fallback check)
                for player in gs.players:
                    if not player.hand.original_cards or len(player.hand.original_cards) < 2:
                        # Fallback: redeal if something went wrong
                        player.hand.original_cards = gs.deck.draw_n(2)

                # Transition to RIVER phase for actual gameplay
                gs.phase = GamePhase.RIVER
                gs.current_action_step = 0
                first_to_act = (gs.button_seat + 1) % len(gs.players)
                gs.current_player_seat = first_to_act

                # Initialize action tracking for RIVER phase
                gs.players_acted_this_step.clear()
                gs.current_highest_normal = 0

                gs.draw_phase_step = 0
                gs.draw_phase_timestamp = None

    def execute_showdown(self) -> Dict[str, int]:
        """Evaluate hands and distribute pots. Returns {player_id: winnings}"""
        gs = self.game_state
        assert gs is not None

        payouts = defaultdict(int)

        # Collect non-folded hands
        hands_by_seat: Dict[int, List[HandValue]] = {}
        for player in gs.players:
            if player.is_active and player.hand and not player.hand.folded:
                hands_by_seat[player.seat] = player.hand.all_hands()

        if not hands_by_seat:
            return dict(payouts)

        # Main pot distribution
        winner_seat = self._find_best_hand(hands_by_seat)
        if winner_seat is not None:
            payouts[gs.players[winner_seat].player_id] += gs.normal_pot

        # Escrow pot distribution (simplified: same winner for now)
        if gs.escrow_pot > 0 and winner_seat is not None:
            payouts[gs.players[winner_seat].player_id] += gs.escrow_pot

        return dict(payouts)

    def _find_best_hand(self, hands_by_seat: Dict[int, List[HandValue]]) -> Optional[int]:
        """Find winning seat"""
        best_seat = None
        best_rank = (-1, -1, -1)

        for seat, hands in hands_by_seat.items():
            hand = hands[0]  # Main hand
            rank = hand.rank_order()
            if rank > best_rank:
                best_rank = rank
                best_seat = seat

        return best_seat

    def get_state(self) -> Dict:
        """Export game state as JSON-serializable dict (for backward compatibility)"""
        if not self.game_state:
            return {}

        gs = self.game_state

        # Progress DRAW phase if active (automatic button determination)
        if gs.phase == GamePhase.DRAW:
            self.progress_button_determination_draw()

        return {
            "hand_number": gs.hand_number,
            "phase": gs.phase.value,
            "button_seat": gs.button_seat,
            "current_player_seat": gs.current_player_seat,
            "current_action_step": gs.current_action_step,
            "normal_pot": gs.normal_pot,
            "escrow_pot": gs.escrow_pot,
            "current_highest_normal": gs.current_highest_normal,
            "players": [
                {
                    "seat": p.seat,
                    "player_id": p.player_id,
                    "username": p.username,
                    "stack": p.stack,
                    "normal_circle": p.normal_circle,
                    "escrow_circle": p.escrow_circle,
                    "is_active": p.is_active,
                    "is_button": p.is_button,
                    "is_folded": p.hand.folded if p.hand else False,
                    "escrow_locked": p.hand.escrow_locked if p.hand else False,
                    "cards": [str(c) for c in (p.hand.original_cards if p.hand else [])],
                    "draw_cards": [str(c) for c in (p.hand.draw_cards if hasattr(p.hand, 'draw_cards') and p.hand.draw_cards else [])],
                    "exposed_card": str(p.hand.exposed_card) if p.hand and p.hand.exposed_card else None,
                }
                for p in gs.players
            ],
            "action_history": gs.action_history,
        }

    def get_state_for_player(self, player_id: str) -> Dict:
        """Get game state with hidden information protected"""
        gs = self.game_state
        assert gs is not None

        player = next((p for p in gs.players if p.player_id == player_id), None)
        my_seat = player.seat if player else None

        return {
            "phase": gs.phase.value,
            "hand_number": gs.hand_number,
            "button_seat": gs.button_seat,
            "current_player_seat": gs.current_player_seat,
            "current_action_step": gs.current_action_step,
            "normal_pot": gs.normal_pot,
            "escrow_pot": gs.escrow_pot,
            "players": [
                self._player_view(p, my_seat)
                for p in gs.players
            ],
        }

    def _player_view(self, player: PlayerState, viewer_seat: Optional[int]) -> Dict:
        """Generate player view respecting hidden information"""
        view = {
            "seat": player.seat,
            "player_id": player.player_id,
            "username": player.username,
            "stack": player.stack,
            "normal_circle": player.normal_circle,
            "escrow_circle": player.escrow_circle,
            "is_button": player.is_button,
            "is_folded": player.hand.folded if player.hand else False,
            "exposed_card": str(player.hand.exposed_card) if player.hand and player.hand.exposed_card else None,
        }

        # Only show own hole cards
        if viewer_seat == player.seat and player.hand:
            view["hole_cards"] = [str(c) for c in player.hand.original_cards]
        else:
            view["hole_cards"] = None

        return view
