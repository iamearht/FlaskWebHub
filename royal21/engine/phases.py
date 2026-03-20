"""Game phase definitions."""

from enum import Enum


class GamePhase(str, Enum):
    """Enum for game phases."""
    SETUP = "SETUP"              # Waiting for players to join
    ANTES = "ANTES"              # Players post antes and blinds
    DEAL = "DEAL"                # Deal 2 cards to each player
    BETTING_1 = "BETTING_1"      # First betting round (players reveal 1 card)
    DRAW = "DRAW"                # Optional draw phase (0-1 card per player)
    BETTING_2 = "BETTING_2"      # Second betting round
    SHOWDOWN = "SHOWDOWN"        # Remaining players reveal; winner determined
    HAND_END = "HAND_END"        # Hand concluded; chips distributed


# Phase progression
PHASE_SEQUENCE = [
    GamePhase.SETUP,
    GamePhase.ANTES,
    GamePhase.DEAL,
    GamePhase.BETTING_1,
    GamePhase.DRAW,
    GamePhase.BETTING_2,
    GamePhase.SHOWDOWN,
    GamePhase.HAND_END,
]


def next_phase(current: GamePhase) -> GamePhase:
    """Get the next phase in sequence."""
    try:
        idx = PHASE_SEQUENCE.index(current)
        return PHASE_SEQUENCE[idx + 1]
    except (ValueError, IndexError):
        return GamePhase.SETUP
