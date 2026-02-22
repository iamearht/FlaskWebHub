import secrets
import math
import time
import random
from typing import Any, Dict, List, Optional, Tuple

from extensions import db
from models import (
    Match,
    MatchState,
    MatchDrawDeckCard,
    MatchDrawCard,
    MatchTurn,
    MatchTurnDeckCard,
    MatchRound,
    MatchDealerCard,
    MatchBox,
    MatchHand,
    MatchHandCard,
    MatchHandInsurance,
    MatchTurnResult,
    CARD_RANKS,
    CARD_SUITS,
)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

CARD_VALUES = {
    '2': 2, '3': 3, '4': 3+1, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11
}

DRAW_RANK_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14, 'JOKER': 15
}

CUT_CARD_POSITION = 65
TURN_STARTING_CHIPS = 100
DECISION_TIMEOUT = 30
ROUND_RESULT_TIMEOUT = 5

RANK_TO_CODE = {r: i for i, r in enumerate(CARD_RANKS)}
CODE_TO_RANK = {i: r for i, r in enumerate(CARD_RANKS)}
SUIT_TO_CODE = {s: i for i, s in enumerate(CARD_SUITS)}
CODE_TO_SUIT = {i: s for i, s in enumerate(CARD_SUITS)}

# -----------------------------------------------------------------------------
# Public Game Modes (for lobby display)
# -----------------------------------------------------------------------------

GAME_MODES = {
    "classic": {
        "name": "Classic",
        "description": "Standard blackjack rules."
    },
    "classic_joker": {
        "name": "Classic Joker",
        "description": "Classic blackjack with jokers."
    },
    "interactive": {
        "name": "Interactive",
        "description": "Players control dealer actions."
    },
    "interactive_joker": {
        "name": "Interactive Joker",
        "description": "Interactive mode with jokers."
    },
}
# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def _secure_shuffle(lst: List[Any]) -> None:
    for i in range(len(lst) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        lst[i], lst[j] = lst[j], lst[i]


def create_deck(joker: bool = False) -> List[Dict[str, str]]:
    deck: List[Dict[str, str]] = []
    for _ in range(2):
        for suit in SUITS:
            for rank in RANKS:
                deck.append({'rank': rank, 'suit': suit})
    if joker:
        for _ in range(4):
            deck.append({'rank': 'JOKER', 'suit': 'joker'})
    _secure_shuffle(deck)
    return deck


def _is_joker_mode(game_mode: str) -> bool:
    return game_mode in ('classic_joker', 'interactive_joker')


def _is_classic_mode(game_mode: str) -> bool:
    return game_mode in ('classic', 'classic_joker')


def _codes_to_card(rank_code: int, suit_code: int, chosen_value: Optional[int] = None) -> Dict[str, Any]:
    card = {'rank': CODE_TO_RANK[int(rank_code)], 'suit': CODE_TO_SUIT[int(suit_code)]}
    if chosen_value is not None:
        card['chosen_value'] = int(chosen_value)
    return card


def _card_to_codes(card: Dict[str, Any]) -> Tuple[int, int]:
    rank = card['rank']
    suit = card['suit']
    if rank not in RANK_TO_CODE:
        raise ValueError(f"Unknown rank: {rank}")
    if suit not in SUIT_TO_CODE:
        raise ValueError(f"Unknown suit: {suit}")
    return RANK_TO_CODE[rank], SUIT_TO_CODE[suit]


def _get_match_state(match_id: int) -> MatchState:
    ms = MatchState.query.filter_by(match_id=match_id).first()
    if not ms:
        raise ValueError("MatchState not initialized for this match")
    return ms


def _get_turn(match_id: int, turn_index: int) -> MatchTurn:
    t = MatchTurn.query.filter_by(match_id=match_id, turn_index=turn_index).first()
    if not t:
        raise ValueError("MatchTurn not found")
    return t


def _get_active_round(match_id: int, turn_index: int) -> Optional[MatchRound]:
    t = _get_turn(match_id, turn_index)
    if t.active_round_index is None:
        return None
    return MatchRound.query.filter_by(
        match_id=match_id,
        turn_index=turn_index,
        round_index=int(t.active_round_index),
    ).first()


def _get_hand(match_id: int, turn_index: int, round_index: int, box_index: int, hand_index: int) -> MatchHand:
    h = MatchHand.query.filter_by(
        match_id=match_id,
        turn_index=turn_index,
        round_index=round_index,
        box_index=box_index,
        hand_index=hand_index
    ).first()
    if not h:
        raise ValueError("MatchHand not found")
    return h


def _hand_cards(match_id: int, turn_index: int, round_index: int, box_index: int, hand_index: int) -> List[Dict[str, Any]]:
    rows = (
        MatchHandCard.query.filter_by(
            match_id=match_id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_index,
            hand_index=hand_index
        )
        .order_by(MatchHandCard.seq.asc())
        .all()
    )
    return [_codes_to_card(r.rank_code, r.suit_code, r.joker_chosen_value) for r in rows]


def _dealer_cards(match_id: int, turn_index: int, round_index: int) -> List[Dict[str, Any]]:
    rows = (
        MatchDealerCard.query.filter_by(
            match_id=match_id,
            turn_index=turn_index,
            round_index=round_index
        )
        .order_by(MatchDealerCard.seq.asc())
        .all()
    )
    return [_codes_to_card(r.rank_code, r.suit_code, r.joker_chosen_value) for r in rows]


def _has_unassigned_jokers(cards: List[Dict[str, Any]]) -> bool:
    return any(c['rank'] == 'JOKER' and 'chosen_value' not in c for c in cards)


def _unassigned_joker_seqs_for_hand(match_id: int, turn_index: int, round_index: int, box_index: int, hand_index: int) -> List[int]:
    rows = (
        MatchHandCard.query.filter_by(
            match_id=match_id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_index,
            hand_index=hand_index,
            rank_code=RANK_TO_CODE['JOKER'],
        )
        .order_by(MatchHandCard.seq.asc())
        .all()
    )
    return [int(r.seq) for r in rows if r.joker_chosen_value is None]


def _unassigned_joker_seqs_for_dealer(match_id: int, turn_index: int, round_index: int) -> List[int]:
    rows = (
        MatchDealerCard.query.filter_by(
            match_id=match_id,
            turn_index=turn_index,
            round_index=round_index,
            rank_code=RANK_TO_CODE['JOKER'],
        )
        .order_by(MatchDealerCard.seq.asc())
        .all()
    )
    return [int(r.seq) for r in rows if r.joker_chosen_value is None]


def hand_value(cards: List[Dict[str, Any]]) -> int:
    total = 0
    aces = 0
    jokers_auto = 0

    for c in cards:
        if c['rank'] == 'JOKER':
            if 'chosen_value' in c:
                total += int(c['chosen_value'])
            else:
                jokers_auto += 1
            continue
        total += CARD_VALUES[c['rank']]
        if c['rank'] == 'A':
            aces += 1

    while total > 21 and aces > 0:
        total -= 10
        aces -= 1

    # auto-value any remaining jokers (when allowed)
    for _ in range(jokers_auto):
        best = 21 - total
        best = min(11, max(1, best))
        total += best

    return total


def is_ten_value(rank: str) -> bool:
    return rank in ('10', 'J', 'Q', 'K')


def is_blackjack(cards: List[Dict[str, Any]]) -> bool:
    if _has_unassigned_jokers(cards):
        return False
    return len(cards) == 2 and hand_value(cards) == 21


def _no_blackjack_after_split(hand: MatchHand) -> bool:
    return bool(hand.from_split_aces) or bool(hand.from_split_jokers)


def _can_double(hand_cards_list: List[Dict[str, Any]], chips: int, bet: int) -> bool:
    return len(hand_cards_list) == 2 and chips >= bet


def _can_split(hand_cards_list: List[Dict[str, Any]], chips: int, bet: int) -> bool:
    if len(hand_cards_list) != 2:
        return False
    r1, r2 = hand_cards_list[0]['rank'], hand_cards_list[1]['rank']
    same_rank = r1 == r2
    both_tens = is_ten_value(r1) and is_ten_value(r2)
    return (same_rank or both_tens) and chips >= bet


def _auto_assign_jokers_in_place(cards: List[Dict[str, Any]]) -> None:
    """
    Matches your old engine's classic-mode dealer joker auto-assignment.
    """
    total = 0
    aces = 0

    # compute total excluding unassigned jokers
    for c in cards:
        if c['rank'] == 'JOKER':
            if 'chosen_value' in c:
                total += int(c['chosen_value'])
            continue
        total += CARD_VALUES[c['rank']]
        if c['rank'] == 'A':
            aces += 1

    while total > 21 and aces > 0:
        total -= 10
        aces -= 1

    for c in cards:
        if c['rank'] == 'JOKER' and 'chosen_value' not in c:
            best = 21 - total
            best = min(11, max(1, best))
            c['chosen_value'] = best
            total += best


# -----------------------------------------------------------------------------
# Phase + state machine (SQL-only)
# -----------------------------------------------------------------------------

def init_game_state(match: Match, is_heads_up: bool = False) -> None:
    """
    Initializes normalized SQL state for a match.
    Creates draw deck and runs draws until winner exists.
    """

    # wipe any existing normalized rows for a clean start
    mid = match.id
    if not mid:
        raise ValueError("Match must be persisted before init_game_state")

    for tbl in (
        MatchDrawDeckCard, MatchDrawCard,
        MatchTurn, MatchTurnDeckCard,
        MatchRound, MatchDealerCard,
        MatchBox, MatchHand, MatchHandCard,
        MatchHandInsurance, MatchTurnResult,
        MatchState,
    ):
        db.session.query(tbl).filter_by(match_id=mid).delete(synchronize_session=False)

    ms = MatchState(
        match_id=mid,
        phase='CARD_DRAW',
        is_heads_up=bool(is_heads_up),
        draw_deck_pos=0,
        draw_winner=None,
        chooser=None,
        choice_made=False,
        draw_timestamp=time.time(),
        current_turn=0,
        match_over=False,
        match_result_winner=None,
        match_result_reason=None,
    )
    db.session.add(ms)

    # create draw deck rows
    deck = create_deck(joker=_is_joker_mode(match.game_mode))
    for pos, c in enumerate(deck):
        r, s = _card_to_codes(c)
        db.session.add(MatchDrawDeckCard(match_id=mid, pos=pos, rank_code=r, suit_code=s))

    db.session.flush()

    # keep drawing until winner
    safety = 0
    while ms.draw_winner is None:
        do_card_draw(match, commit=False)
        ms = _get_match_state(mid)
        safety += 1
        if safety > 500:
            raise RuntimeError("Draw loop exceeded safety limit")

    db.session.commit()


def do_card_draw(match: Match, commit: bool = True) -> None:
    ms = _get_match_state(match.id)
    if ms.phase != 'CARD_DRAW':
        raise ValueError("Not in CARD_DRAW phase")

    # load deck size
    deck_count = MatchDrawDeckCard.query.filter_by(match_id=match.id).count()
    pos = int(ms.draw_deck_pos)

    # reshuffle draw deck if needed
    if pos + 2 > deck_count or deck_count == 0:
        db.session.query(MatchDrawDeckCard).filter_by(match_id=match.id).delete(synchronize_session=False)
        db.session.query(MatchDrawCard).filter_by(match_id=match.id).delete(synchronize_session=False)

        ms.draw_deck_pos = 0
        ms.draw_winner = None
        ms.chooser = None
        ms.draw_timestamp = time.time()

        deck = create_deck(joker=_is_joker_mode(match.game_mode))
        for p, c in enumerate(deck):
            r, s = _card_to_codes(c)
            db.session.add(MatchDrawDeckCard(match_id=match.id, pos=p, rank_code=r, suit_code=s))

        db.session.flush()
        deck_count = len(deck)
        pos = 0

    c1 = MatchDrawDeckCard.query.filter_by(match_id=match.id, pos=pos).first()
    c2 = MatchDrawDeckCard.query.filter_by(match_id=match.id, pos=pos + 1).first()
    if not c1 or not c2:
        raise RuntimeError("Draw deck corrupted")

    ms.draw_deck_pos = pos + 2

    # append drawn cards per player (seq increments)
    p1_seq = MatchDrawCard.query.filter_by(match_id=match.id, player_num=1).count()
    p2_seq = MatchDrawCard.query.filter_by(match_id=match.id, player_num=2).count()

    db.session.add(MatchDrawCard(match_id=match.id, player_num=1, seq=p1_seq, rank_code=c1.rank_code, suit_code=c1.suit_code))
    db.session.add(MatchDrawCard(match_id=match.id, player_num=2, seq=p2_seq, rank_code=c2.rank_code, suit_code=c2.suit_code))

    r1 = CODE_TO_RANK[int(c1.rank_code)]
    r2 = CODE_TO_RANK[int(c2.rank_code)]
    v1 = DRAW_RANK_VALUES.get(r1, 0)
    v2 = DRAW_RANK_VALUES.get(r2, 0)

    if v1 > v2:
        ms.draw_winner = 1
        ms.chooser = 1
        ms.phase = 'CHOICE'
        set_decision_timer(match, "CHOICE")
    elif v2 > v1:
        ms.draw_winner = 2
        ms.chooser = 2
        ms.phase = 'CHOICE'
        set_decision_timer(match, "CHOICE")
    else:
        ms.draw_winner = None

    if commit:
        db.session.commit()


def make_choice(match: Match, chooser_goes_first_as_player: bool) -> None:
    ms = _get_match_state(match.id)
    if ms.phase != 'CHOICE':
        raise ValueError("Not in CHOICE phase")
    if ms.chooser not in (1, 2):
        raise ValueError("Chooser not set")

    chooser = int(ms.chooser)
    other = 2 if chooser == 1 else 1

    if chooser_goes_first_as_player:
        first_player, first_bank = chooser, other
    else:
        first_player, first_bank = other, chooser

    is_heads_up = bool(ms.is_heads_up)

    turns: List[Tuple[int, int]] = []
    if is_heads_up:
        turns = [
            (first_player, first_bank),
            (first_bank, first_player),
            (first_bank, first_player),
            (first_player, first_bank),
            (first_player, first_bank),
            (first_bank, first_player),
            (first_bank, first_player),
            (first_player, first_bank),
        ]
    else:
        turns = [
            (first_player, first_bank),
            (first_bank, first_player),
            (first_bank, first_player),
            (first_player, first_bank),
        ]

    # clear any old turns for safety
    db.session.query(MatchTurn).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchTurnDeckCard).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchRound).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchDealerCard).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchBox).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchHand).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchHandCard).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchHandInsurance).filter_by(match_id=match.id).delete(synchronize_session=False)
    db.session.query(MatchTurnResult).filter_by(match_id=match.id).delete(synchronize_session=False)

    for i, (pr, dr) in enumerate(turns):
        db.session.add(MatchTurn(
            match_id=match.id,
            turn_index=i,
            player_role=pr,
            dealer_role=dr,
            starting_chips=TURN_STARTING_CHIPS,
            chips=TURN_STARTING_CHIPS,
            cards_dealt=0,
            cut_card_reached=False,
            active_round_index=None
        ))

    ms.choice_made = True
    ms.current_turn = 0
    clear_decision_timer(match)

    db.session.commit()
    enter_turn(match)


def enter_turn(match: Match) -> None:
    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)

    # compute starting chips using last result for this player's prior turns
    last = (
        MatchTurnResult.query
        .filter_by(match_id=match.id, player_num=int(t.player_role))
        .order_by(MatchTurnResult.turn_number.desc())
        .first()
    )
    starting_chips = (int(last.chips_end) + TURN_STARTING_CHIPS) if last else TURN_STARTING_CHIPS

    # reset turn row state
    t.starting_chips = starting_chips
    t.chips = starting_chips
    t.cards_dealt = 0
    t.cut_card_reached = False
    t.active_round_index = None

    # rebuild deck rows for this turn
    db.session.query(MatchTurnDeckCard).filter_by(match_id=match.id, turn_index=turn_index).delete(synchronize_session=False)

    deck = create_deck(joker=_is_joker_mode(match.game_mode))
    for pos, c in enumerate(deck):
        r, s = _card_to_codes(c)
        db.session.add(MatchTurnDeckCard(match_id=match.id, turn_index=turn_index, pos=pos, rank_code=r, suit_code=s))

    ms.phase = 'WAITING_BETS'
    set_decision_timer(match, "BET")
    db.session.commit()


def place_bets(match: Match, bets: List[int]) -> None:
    ms = _get_match_state(match.id)
    if ms.phase != 'WAITING_BETS':
        raise ValueError("Not in WAITING_BETS phase")

    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)

    if not bets or len(bets) < 1 or len(bets) > 3:
        raise ValueError("Must place 1-3 bets")

    valid_bets: List[int] = []
    total_bet = 0
    for b in bets:
        amt = int(b)
        if amt < 1:
            raise ValueError("Minimum bet per box is 1")
        total_bet += amt
        valid_bets.append(amt)

    if total_bet > int(t.chips):
        raise ValueError("Total bet exceeds available chips")

    # determine next round index
    last_round = (
        MatchRound.query.filter_by(match_id=match.id, turn_index=turn_index)
        .order_by(MatchRound.round_index.desc())
        .first()
    )
    round_index = (int(last_round.round_index) + 1) if last_round else 0

    # subtract chips
    t.chips = int(t.chips) - total_bet

    rnd = MatchRound(
        match_id=match.id,
        turn_index=turn_index,
        round_index=round_index,
        current_box=0,
        current_hand=0,
        insurance_offered=False,
        total_initial_bet=total_bet,
        resolved=False,
    )
    db.session.add(rnd)

    t.active_round_index = round_index

    # clean any old rows at this round index (safety)
    db.session.query(MatchDealerCard).filter_by(match_id=match.id, turn_index=turn_index, round_index=round_index).delete(synchronize_session=False)
    db.session.query(MatchBox).filter_by(match_id=match.id, turn_index=turn_index, round_index=round_index).delete(synchronize_session=False)
    db.session.query(MatchHand).filter_by(match_id=match.id, turn_index=turn_index, round_index=round_index).delete(synchronize_session=False)
    db.session.query(MatchHandCard).filter_by(match_id=match.id, turn_index=turn_index, round_index=round_index).delete(synchronize_session=False)
    db.session.query(MatchHandInsurance).filter_by(match_id=match.id, turn_index=turn_index, round_index=round_index).delete(synchronize_session=False)

    # deal hands
    for box_i, bet_amt in enumerate(valid_bets):
        db.session.add(MatchBox(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_i,
            bet=bet_amt,
        ))

        hand = MatchHand(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_i,
            hand_index=0,
            bet=bet_amt,
            status='active',
            result=None,
            is_split=False,
            is_doubled=False,
            from_split_aces=False,
            from_split_jokers=False,
        )
        db.session.add(hand)

        # insurance row exists for every hand
        db.session.add(MatchHandInsurance(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_i,
            hand_index=0,
            offered=False,
            taken=False,
            amount=0,
            decided=False,
        ))

        for seq in (0, 1):
            deck_card = MatchTurnDeckCard.query.filter_by(match_id=match.id, turn_index=turn_index, pos=int(t.cards_dealt)).first()
            if not deck_card:
                raise RuntimeError("Turn deck depleted")
            db.session.add(MatchHandCard(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=box_i,
                hand_index=0,
                seq=seq,
                rank_code=deck_card.rank_code,
                suit_code=deck_card.suit_code,
                joker_chosen_value=None,
            ))
            t.cards_dealt = int(t.cards_dealt) + 1

    # deal dealer 2 cards
    for seq in (0, 1):
        deck_card = MatchTurnDeckCard.query.filter_by(match_id=match.id, turn_index=turn_index, pos=int(t.cards_dealt)).first()
        if not deck_card:
            raise RuntimeError("Turn deck depleted")
        db.session.add(MatchDealerCard(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            seq=seq,
            rank_code=deck_card.rank_code,
            suit_code=deck_card.suit_code,
            joker_chosen_value=None,
        ))
        t.cards_dealt = int(t.cards_dealt) + 1

    if int(t.cards_dealt) >= CUT_CARD_POSITION:
        t.cut_card_reached = True

    # insurance logic
    dealer = _dealer_cards(match.id, turn_index, round_index)
    dealer_up = dealer[0]['rank']

    if dealer_up in ('A', 'JOKER'):
        rnd.insurance_offered = True
        # mark insurance offered for all hands
        db.session.query(MatchHandInsurance).filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
        ).update({'offered': True}, synchronize_session=False)
        ms.phase = 'INSURANCE'
        db.session.commit()
        return

    # dealer blackjack immediately if ten-up and blackjack
    if is_ten_value(dealer_up) and is_blackjack(dealer):
        _resolve_dealer_blackjack(match, turn_index, round_index)
        db.session.commit()
        return

    # mark player blackjacks that are already deterministically blackjack
    _mark_player_blackjacks(match, turn_index, round_index)

    ms.phase = 'PLAYER_TURN'
    db.session.commit()
    _advance_to_active(match)


def _mark_player_blackjacks(match: Match, turn_index: int, round_index: int) -> None:
    hands = MatchHand.query.filter_by(match_id=match.id, turn_index=turn_index, round_index=round_index).all()
    for h in hands:
        cards = _hand_cards(match.id, turn_index, round_index, int(h.box_index), int(h.hand_index))
        if is_blackjack(cards) and not _no_blackjack_after_split(h):
            h.status = 'blackjack'


def _resolve_dealer_blackjack(match: Match, turn_index: int, round_index: int) -> None:
    """
    Resolve round immediately when dealer has blackjack.
    Transitions safely into ROUND_RESULT with 5-second timer.
    """

    ms = _get_match_state(match.id)
    t = _get_turn(match.id, turn_index)

    rnd = MatchRound.query.filter_by(
        match_id=match.id,
        turn_index=turn_index,
        round_index=round_index
    ).first()

    if not rnd:
        raise ValueError("Round missing")

    hands = MatchHand.query.filter_by(
        match_id=match.id,
        turn_index=turn_index,
        round_index=round_index
    ).all()

    for h in hands:
        cards = _hand_cards(
            match.id,
            turn_index,
            round_index,
            int(h.box_index),
            int(h.hand_index)
        )

        # Player blackjack vs dealer blackjack → push
        if is_blackjack(cards) and not _no_blackjack_after_split(h):
            t.chips = int(t.chips) + int(h.bet)
            h.status = 'push'
            h.result = 'push'
        else:
            h.status = 'lose'
            h.result = 'lose'

    # Mark round resolved
    rnd.resolved = True

    # 🔒 Critical: enter ROUND_RESULT with timer
    ms.phase = 'ROUND_RESULT'
    set_decision_timer(match, "NEXT")

    db.session.commit()


def handle_insurance(match: Match, decisions: List[bool]) -> None:
    """
    Resolve insurance decisions and transition safely.
    Fully timeout-safe and deterministic.
    """

    ms = _get_match_state(match.id)

    if ms.phase != 'INSURANCE':
        raise ValueError("Not in INSURANCE phase")

    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)
    rnd = _get_active_round(match.id, turn_index)

    if not rnd:
        raise ValueError("No active round")

    round_index = int(rnd.round_index)

    # Enumerate hands in deterministic order
    hands = (
        MatchHand.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index
        )
        .order_by(MatchHand.box_index.asc(), MatchHand.hand_index.asc())
        .all()
    )

    # Pad decisions if shorter
    if len(decisions) < len(hands):
        decisions = decisions + [False] * (len(hands) - len(decisions))

    # ---------------------------------------
    # Apply insurance decisions
    # ---------------------------------------
    for i, h in enumerate(hands):
        ins = MatchHandInsurance.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=int(h.box_index),
            hand_index=int(h.hand_index),
        ).first()

        if not ins:
            continue

        take = bool(decisions[i])

        if take and ins.offered and not ins.decided:
            ins_amount = max(1, math.floor(int(h.bet) / 2))
            ins_amount = min(ins_amount, int(t.chips))

            t.chips = int(t.chips) - ins_amount
            ins.taken = True
            ins.amount = ins_amount

        ins.decided = True

    dealer = _dealer_cards(match.id, turn_index, round_index)

    # ---------------------------------------
    # Dealer has blackjack
    # ---------------------------------------
    if is_blackjack(dealer):

        for h in hands:
            ins = MatchHandInsurance.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=int(h.box_index),
                hand_index=int(h.hand_index),
            ).first()

            # Pay insurance (2:1 + original stake returned)
            if ins and ins.taken:
                t.chips = int(t.chips) + int(ins.amount) * 3

            cards = _hand_cards(
                match.id,
                turn_index,
                round_index,
                int(h.box_index),
                int(h.hand_index)
            )

            if is_blackjack(cards) and not _no_blackjack_after_split(h):
                t.chips = int(t.chips) + int(h.bet)
                h.status = 'push'
                h.result = 'push'
            else:
                h.status = 'lose'
                h.result = 'lose'

        rnd.resolved = True

        # 🔒 Critical: enter result phase with 5-second timer
        ms.phase = 'ROUND_RESULT'
        set_decision_timer(match, "NEXT")

        db.session.commit()
        return

    # ---------------------------------------
    # No dealer blackjack → continue to player phase
    # ---------------------------------------
    _mark_player_blackjacks(match, turn_index, round_index)

    ms.phase = 'PLAYER_TURN'
    db.session.commit()

    # advance_to_active() sets the ACTION/JOKER timer
    _advance_to_active(match)


def _advance_to_active(match: Match) -> None:
    """
    Move round current_box/current_hand to the next 'active' hand.
    If none remain, play dealer / resolve.
    """

    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    rnd = _get_active_round(match.id, turn_index)

    if not rnd:
        return

    round_index = int(rnd.round_index)
    game_mode = match.game_mode

    # boxes in order
    boxes = (
        MatchBox.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index
        )
        .order_by(MatchBox.box_index.asc())
        .all()
    )

    for b in boxes:
        bi = int(b.box_index)

        hands = (
            MatchHand.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=bi
            )
            .order_by(MatchHand.hand_index.asc())
            .all()
        )

        for h in hands:
            hi = int(h.hand_index)

            if h.status != 'active':
                continue

            cards = _hand_cards(match.id, turn_index, round_index, bi, hi)

            # Auto-stand if already 21 and deterministically valued
            if not _has_unassigned_jokers(cards) and hand_value(cards) == 21:
                h.status = 'stand'
                continue

            # Move pointer to this hand
            rnd.current_box = bi
            rnd.current_hand = hi

            # ---- JOKER CHOICE ----
            if _is_joker_mode(game_mode) and _has_unassigned_jokers(cards):
                ms.phase = 'JOKER_CHOICE'
                set_decision_timer(match, "JOKER")
                db.session.commit()
                return

            # ---- PLAYER TURN ----
            ms.phase = 'PLAYER_TURN'
            set_decision_timer(match, "ACTION")
            db.session.commit()
            return

    # No active hands left → dealer stage
    db.session.commit()
    _play_dealer(match)


def player_action(match: Match, action: str) -> None:
    ms = _get_match_state(match.id)

    if ms.phase != 'PLAYER_TURN':
        raise ValueError("Not in PLAYER_TURN phase")

    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)
    rnd = _get_active_round(match.id, turn_index)

    if not rnd:
        raise ValueError("No active round")

    round_index = int(rnd.round_index)
    box_index = int(rnd.current_box)
    hand_index = int(rnd.current_hand)

    h = _get_hand(match.id, turn_index, round_index, box_index, hand_index)

    if h.status != 'active':
        raise ValueError("No active hand")

    cards = _hand_cards(match.id, turn_index, round_index, box_index, hand_index)
    game_mode = match.game_mode

    def _draw_to_hand() -> Tuple[str, bool]:
        deck_card = MatchTurnDeckCard.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            pos=int(t.cards_dealt)
        ).first()

        if not deck_card:
            raise RuntimeError("Turn deck depleted")

        seq = MatchHandCard.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_index,
            hand_index=hand_index
        ).count()

        db.session.add(MatchHandCard(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_index,
            hand_index=hand_index,
            seq=seq,
            rank_code=deck_card.rank_code,
            suit_code=deck_card.suit_code,
            joker_chosen_value=None,
        ))

        t.cards_dealt = int(t.cards_dealt) + 1
        if int(t.cards_dealt) >= CUT_CARD_POSITION:
            t.cut_card_reached = True

        rank = CODE_TO_RANK[int(deck_card.rank_code)]
        is_unassigned_joker = (rank == 'JOKER')

        return rank, is_unassigned_joker

    # --------------------------------------------------
    # HIT
    # --------------------------------------------------
    if action == 'hit':
        rank, joker = _draw_to_hand()
        db.session.commit()

        cards = _hand_cards(match.id, turn_index, round_index, box_index, hand_index)

        # Joker branch
        if _is_joker_mode(game_mode) and joker and _has_unassigned_jokers(cards):
            ms.phase = 'JOKER_CHOICE'
            set_decision_timer(match, "JOKER")
            db.session.commit()
            return

        val = hand_value(cards)

        if val > 21:
            h.status = 'bust'
            db.session.commit()
            _next_hand(match)
            return

        if val == 21:
            h.status = 'stand'
            db.session.commit()
            _next_hand(match)
            return

        # Still active → refresh timer
        set_decision_timer(match, "ACTION")
        db.session.commit()
        return

    # --------------------------------------------------
    # STAND
    # --------------------------------------------------
    if action == 'stand':
        h.status = 'stand'
        db.session.commit()
        _next_hand(match)
        return

    # --------------------------------------------------
    # DOUBLE
    # --------------------------------------------------
    if action == 'double':
        if not _can_double(cards, int(t.chips), int(h.bet)):
            raise ValueError("Cannot double")

        t.chips = int(t.chips) - int(h.bet)
        h.bet = int(h.bet) * 2
        h.is_doubled = True

        rank, joker = _draw_to_hand()
        db.session.commit()

        cards = _hand_cards(match.id, turn_index, round_index, box_index, hand_index)

        if _is_joker_mode(game_mode) and joker and _has_unassigned_jokers(cards):
            ms.phase = 'JOKER_CHOICE'
            set_decision_timer(match, "JOKER")
            db.session.commit()
            return

        val = hand_value(cards)

        h.status = 'bust' if val > 21 else 'stand'
        db.session.commit()
        _next_hand(match)
        return

    # --------------------------------------------------
        # SPLIT
        # --------------------------------------------------
            # --------------------------------------------------
    # SPLIT
    # --------------------------------------------------
    if action == 'split':
        # Validate split eligibility
        if h.is_split:
            raise ValueError("Cannot split again")

        if not _can_split(cards, int(t.chips), int(h.bet)):
            raise ValueError("Cannot split")

        # Deduct additional bet for the new hand
        t.chips = int(t.chips) - int(h.bet)

        # Determine the insert index: place new hand immediately after current hand.
        insert_hi = hand_index + 1

        # Shift any existing hands (and dependent rows) up by 1 to make room.
        existing_his = (
            MatchHand.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=box_index
            )
            .with_entities(MatchHand.hand_index)
            .order_by(MatchHand.hand_index.desc())
            .all()
        )
        existing_his = [int(r[0]) for r in existing_his]
        for hi in existing_his:
            if hi >= insert_hi:
                # Hands
                MatchHand.query.filter_by(
                    match_id=match.id,
                    turn_index=turn_index,
                    round_index=round_index,
                    box_index=box_index,
                    hand_index=hi
                ).update({'hand_index': hi + 1})
                # Hand cards
                MatchHandCard.query.filter_by(
                    match_id=match.id,
                    turn_index=turn_index,
                    round_index=round_index,
                    box_index=box_index,
                    hand_index=hi
                ).update({'hand_index': hi + 1})
                # Insurance rows (if any)
                MatchHandInsurance.query.filter_by(
                    match_id=match.id,
                    turn_index=turn_index,
                    round_index=round_index,
                    box_index=box_index,
                    hand_index=hi
                ).update({'hand_index': hi + 1})

        new_hi = insert_hi

        # Create the new hand with duplicated bet
        new_hand = MatchHand(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_index,
            hand_index=new_hi,
            bet=int(h.bet),
            is_split=True,
            is_doubled=False,
            from_split_aces=(cards[0]['rank'] == 'A'),
            from_split_jokers=(cards[0]['rank'] == 'JOKER'),
        )
        db.session.add(new_hand)

        # Mark original hand as a split hand too
        h.is_split = True
        h.from_split_aces = (cards[0]['rank'] == 'A')
        h.from_split_jokers = (cards[0]['rank'] == 'JOKER')

        # Move the second card from original hand to the new hand.
        second_row = MatchHandCard.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            box_index=box_index,
            hand_index=hand_index,
            seq=1
        ).first()
        if not second_row:
            raise RuntimeError("Cannot split: missing second card")

        second_row.hand_index = new_hi
        second_row.seq = 0

        # Draw one card to original hand, then one card to the new hand.
        def _draw_to_specific_hand(target_hi: int) -> bool:
            """Returns True if drawn card is an unassigned joker."""
            deck_card = MatchTurnDeckCard.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                pos=int(t.cards_dealt)
            ).first()
            if not deck_card:
                raise RuntimeError("Turn deck depleted")

            seq = MatchHandCard.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=box_index,
                hand_index=target_hi
            ).count()

            db.session.add(MatchHandCard(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=box_index,
                hand_index=target_hi,
                seq=seq,
                rank_code=deck_card.rank_code,
                suit_code=deck_card.suit_code,
                joker_chosen_value=None,
            ))

            t.cards_dealt = int(t.cards_dealt) + 1
            if int(t.cards_dealt) >= CUT_CARD_POSITION:
                t.cut_card_reached = True

            return CODE_TO_RANK[int(deck_card.rank_code)] == 'JOKER'

        _draw_to_specific_hand(hand_index)
        _draw_to_specific_hand(new_hi)

        # Let the state machine pick the next active hand (and joker-choice phase if needed)
        db.session.flush()
        _advance_to_active(match)
        return

    raise ValueError(f"Unknown action: {action}")




def assign_joker_values(match: Match, values: List[str]) -> None:
    ms = _get_match_state(match.id)
    if ms.phase != 'JOKER_CHOICE':
        raise ValueError("Not in JOKER_CHOICE phase")

    turn_index = int(ms.current_turn)
    rnd = _get_active_round(match.id, turn_index)
    if not rnd:
        raise ValueError("No active round")
    round_index = int(rnd.round_index)

    box_index = int(rnd.current_box)
    hand_index = int(rnd.current_hand)
    h = _get_hand(match.id, turn_index, round_index, box_index, hand_index)

    seqs = _unassigned_joker_seqs_for_hand(match.id, turn_index, round_index, box_index, hand_index)
    if len(values) != len(seqs):
        raise ValueError("Invalid number of joker values")

    VALID = {"A","2","3","4","5","6","7","8","9","10","J","Q","K"}

    for seq, choice in zip(seqs, values):
        if choice not in VALID:
            raise ValueError("Invalid joker value")
        if choice in ("J","Q","K"):
            numeric = 10
        elif choice == "A":
            numeric = 11
        else:
            numeric = int(choice)

        row = MatchHandCard.query.filter_by(
            match_id=match.id, turn_index=turn_index, round_index=round_index,
            box_index=box_index, hand_index=hand_index, seq=seq
        ).first()
        if not row:
            raise RuntimeError("Card missing while assigning joker")
        row.joker_chosen_value = numeric

    db.session.commit()

    cards = _hand_cards(match.id, turn_index, round_index, box_index, hand_index)
    hv = hand_value(cards)

    # If this was a doubled hand that drew a joker, finish immediately
    if bool(h.is_doubled) and len(cards) == 3 and h.status == 'active':
        h.status = 'bust' if hv > 21 else 'stand'
        db.session.commit()
        _next_hand(match)
        return

    if hv > 21:
        h.status = 'bust'
        db.session.commit()
        _next_hand(match)
        return

    if hv == 21:
        h.status = 'stand'
        db.session.commit()
        _next_hand(match)
        return

    ms.phase = 'PLAYER_TURN'
    db.session.commit()


def _next_hand(match: Match) -> None:
    """
    Move to next active hand based on round ordering, then advance_to_active().
    """
    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    rnd = _get_active_round(match.id, turn_index)
    if not rnd:
        return

    # We simply call advance_to_active which scans in-order for active hands
    db.session.commit()
    _advance_to_active(match)


def _play_dealer(match: Match) -> None:
    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)
    rnd = _get_active_round(match.id, turn_index)
    if not rnd:
        return

    round_index = int(rnd.round_index)
    game_mode = match.game_mode

    # --------------------------------------------------
    # 1) If no player hands are standing/blackjack, nothing to compare -> resolve now
    # --------------------------------------------------
    hands = MatchHand.query.filter_by(
        match_id=match.id,
        turn_index=turn_index,
        round_index=round_index
    ).all()

    any_standing = any(h.status in ('stand', 'blackjack') for h in hands)
    if not any_standing:
        _resolve_hands(match)
        return

    dealer = _dealer_cards(match.id, turn_index, round_index)

    # --------------------------------------------------
    # 2) Dealer Joker Handling
    # --------------------------------------------------
    if _is_joker_mode(game_mode) and _has_unassigned_jokers(dealer):
        if _is_classic_mode(game_mode):
            # Classic: auto-assign immediately (no decision phase)
            _auto_assign_jokers_in_place(dealer)

            for seq, c in enumerate(dealer):
                if c.get('rank') == 'JOKER' and 'chosen_value' in c:
                    row = MatchDealerCard.query.filter_by(
                        match_id=match.id,
                        turn_index=turn_index,
                        round_index=round_index,
                        seq=seq
                    ).first()
                    if row and row.joker_chosen_value is None:
                        row.joker_chosen_value = int(c['chosen_value'])

            db.session.commit()
            dealer = _dealer_cards(match.id, turn_index, round_index)

        else:
            # Interactive: must enter dealer joker choice with a timer
            ms.phase = 'DEALER_JOKER_CHOICE'
            set_decision_timer(match, "DEALER_JOKER")
            db.session.commit()
            return

    # --------------------------------------------------
    # 3) Classic Mode — Auto Dealer Play
    # --------------------------------------------------
    if _is_classic_mode(game_mode):
        while hand_value(dealer) < 17:
            deck_card = MatchTurnDeckCard.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                pos=int(t.cards_dealt)
            ).first()

            if not deck_card:
                raise RuntimeError("Turn deck depleted")

            seq = MatchDealerCard.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index
            ).count()

            db.session.add(MatchDealerCard(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                seq=seq,
                rank_code=deck_card.rank_code,
                suit_code=deck_card.suit_code,
                joker_chosen_value=None
            ))

            t.cards_dealt = int(t.cards_dealt) + 1
            if int(t.cards_dealt) >= CUT_CARD_POSITION:
                t.cut_card_reached = True

            db.session.commit()

            dealer = _dealer_cards(match.id, turn_index, round_index)

            # If a joker appears mid-loop in classic joker mode, auto-assign immediately
            if _is_joker_mode(game_mode) and _has_unassigned_jokers(dealer):
                _auto_assign_jokers_in_place(dealer)

                for seq_i, c in enumerate(dealer):
                    if c.get('rank') == 'JOKER' and 'chosen_value' in c:
                        row = MatchDealerCard.query.filter_by(
                            match_id=match.id,
                            turn_index=turn_index,
                            round_index=round_index,
                            seq=seq_i
                        ).first()
                        if row and row.joker_chosen_value is None:
                            row.joker_chosen_value = int(c['chosen_value'])

                db.session.commit()
                dealer = _dealer_cards(match.id, turn_index, round_index)

        _resolve_hands(match)
        return

    # --------------------------------------------------
    # 4) Interactive Mode — Dealer Decision Phase
    # --------------------------------------------------
    dealer_val = hand_value(dealer)

    # Standard blackjack dealer logic: act while < 17; otherwise resolve.
    # (Timeout rule will force 'stand' in DEALER_TURN anyway.)
    if dealer_val < 17:
        ms.phase = 'DEALER_TURN'
        set_decision_timer(match, "ACTION")
        db.session.commit()
        return

    _resolve_hands(match)


def dealer_action(match: Match, action: str) -> None:
    ms = _get_match_state(match.id)

    if ms.phase != 'DEALER_TURN':
        raise ValueError("Not in DEALER_TURN phase")

    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)
    rnd = _get_active_round(match.id, turn_index)

    if not rnd:
        raise ValueError("No active round")

    round_index = int(rnd.round_index)
    game_mode = match.game_mode

    # --------------------------------------------------
    # STAND
    # --------------------------------------------------
    if action == 'stand':
        _resolve_hands(match)
        return

    # --------------------------------------------------
    # HIT
    # --------------------------------------------------
    if action == 'hit':
        deck_card = MatchTurnDeckCard.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            pos=int(t.cards_dealt)
        ).first()

        if not deck_card:
            raise RuntimeError("Turn deck depleted")

        seq = MatchDealerCard.query.filter_by(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index
        ).count()

        db.session.add(MatchDealerCard(
            match_id=match.id,
            turn_index=turn_index,
            round_index=round_index,
            seq=seq,
            rank_code=deck_card.rank_code,
            suit_code=deck_card.suit_code,
            joker_chosen_value=None
        ))

        t.cards_dealt = int(t.cards_dealt) + 1
        if int(t.cards_dealt) >= CUT_CARD_POSITION:
            t.cut_card_reached = True

        db.session.commit()

        dealer = _dealer_cards(match.id, turn_index, round_index)

        # ---- Joker branch ----
        if _is_joker_mode(game_mode) and _has_unassigned_jokers(dealer):
            ms.phase = 'DEALER_JOKER_CHOICE'
            set_decision_timer(match, "DEALER_JOKER")
            db.session.commit()
            return

        dealer_val = hand_value(dealer)

        # Bust or exactly 21 → resolve immediately
        if dealer_val >= 21:
            _resolve_hands(match)
            return

        # Still active → remain in DEALER_TURN and refresh timer
        ms.phase = 'DEALER_TURN'
        set_decision_timer(match, "ACTION")
        db.session.commit()
        return

    raise ValueError(f"Unknown dealer action: {action}")


def assign_dealer_joker_values(match: Match, values: List[str]) -> None:
    ms = _get_match_state(match.id)
    if ms.phase != 'DEALER_JOKER_CHOICE':
        raise ValueError("Not in DEALER_JOKER_CHOICE phase")

    turn_index = int(ms.current_turn)
    rnd = _get_active_round(match.id, turn_index)
    if not rnd:
        raise ValueError("No active round")
    round_index = int(rnd.round_index)

    seqs = _unassigned_joker_seqs_for_dealer(match.id, turn_index, round_index)
    if len(values) != len(seqs):
        raise ValueError("Invalid number of joker values")

    VALID = {"A","2","3","4","5","6","7","8","9","10","J","Q","K"}

    for seq, choice in zip(seqs, values):
        if choice not in VALID:
            raise ValueError("Invalid joker value")
        if choice in ("J","Q","K"):
            numeric = 10
        elif choice == "A":
            numeric = 11
        else:
            numeric = int(choice)

        row = MatchDealerCard.query.filter_by(
            match_id=match.id, turn_index=turn_index, round_index=round_index, seq=seq
        ).first()
        if not row:
            raise RuntimeError("Dealer card missing while assigning joker")
        row.joker_chosen_value = numeric

    db.session.commit()

    ms.phase = 'DEALER_TURN'
    set_decision_timer(match, "ACTION")
    db.session.commit()


def _resolve_hands(match: Match) -> None:
    """
    Resolve all hands for the current round and transition to ROUND_RESULT.
    Guarantees deterministic outcome and sets 5-second result timer.
    """

    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)
    rnd = _get_active_round(match.id, turn_index)

    if not rnd:
        raise ValueError("No active round")

    round_index = int(rnd.round_index)

    dealer_cards = _dealer_cards(match.id, turn_index, round_index)
    dealer_val = hand_value(dealer_cards)
    dealer_bust = dealer_val > 21
    dealer_blackjack = is_blackjack(dealer_cards)

    hands = MatchHand.query.filter_by(
        match_id=match.id,
        turn_index=turn_index,
        round_index=round_index
    ).all()

    for h in hands:
        cards = _hand_cards(
            match.id,
            turn_index,
            round_index,
            int(h.box_index),
            int(h.hand_index)
        )

        # -----------------------------
        # BUST
        # -----------------------------
        if h.status == 'bust':
            h.result = 'lose'
            continue

        # -----------------------------
        # BLACKJACK
        # -----------------------------
        if h.status == 'blackjack':
            if dealer_blackjack:
                t.chips = int(t.chips) + int(h.bet)
                h.result = 'push'
            else:
                payout = int(h.bet) + math.floor(3 * int(h.bet) / 2)
                t.chips = int(t.chips) + payout
                h.result = 'blackjack_win'
            continue

        # -----------------------------
        # STAND
        # -----------------------------
        if h.status == 'stand':
            player_val = hand_value(cards)

            if dealer_bust or player_val > dealer_val:
                t.chips = int(t.chips) + int(h.bet) * 2
                h.result = 'win'
            elif player_val == dealer_val:
                t.chips = int(t.chips) + int(h.bet)
                h.result = 'push'
            else:
                h.result = 'lose'
            continue

        # -----------------------------
        # SAFETY: Any remaining active/unknown
        # -----------------------------
        h.status = 'lose'
        h.result = 'lose'

    # Mark round resolved
    rnd.resolved = True

    # Enter results phase (5 second display rule)
    ms.phase = 'ROUND_RESULT'
    set_decision_timer(match, "NEXT")

    db.session.commit()


def next_round_or_end_turn(match: Match) -> bool:
    """
    Returns True if turn ended, False if a new round begins.
    """
    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)

    if bool(t.cut_card_reached) or int(t.chips) <= 0:
        end_turn(match)
        return True

    # continue same turn, new round
    t.active_round_index = None
    ms.phase = 'WAITING_BETS'
    set_decision_timer(match, "BET")
    db.session.commit()
    return False


def end_turn(match: Match) -> bool:
    """
    End current turn, write MatchTurnResult, advance ms.current_turn.
    Returns True if match is over.
    """
    ms = _get_match_state(match.id)
    turn_index = int(ms.current_turn)
    t = _get_turn(match.id, turn_index)

    # record result for the *player_role* of this turn
    player_num = int(t.player_role)
    last = (
        MatchTurnResult.query.filter_by(match_id=match.id, player_num=player_num)
        .order_by(MatchTurnResult.turn_number.desc())
        .first()
    )
    turn_number = (int(last.turn_number) + 1) if last else 1

    db.session.merge(MatchTurnResult(
        match_id=match.id,
        player_num=player_num,
        turn_number=turn_number,
        chips_end=int(t.chips),
    ))

    # advance
    ms.current_turn = int(ms.current_turn) + 1

    total_turns = MatchTurn.query.filter_by(match_id=match.id).count()
    if int(ms.current_turn) >= total_turns:
        # match over
        ms.match_over = True

        # last chips for each player
        p1_last = (
            MatchTurnResult.query.filter_by(match_id=match.id, player_num=1)
            .order_by(MatchTurnResult.turn_number.desc()).first()
        )
        p2_last = (
            MatchTurnResult.query.filter_by(match_id=match.id, player_num=2)
            .order_by(MatchTurnResult.turn_number.desc()).first()
        )
        p1 = int(p1_last.chips_end) if p1_last else 0
        p2 = int(p2_last.chips_end) if p2_last else 0

        if p1 > p2:
            winner = 1
        elif p2 > p1:
            winner = 2
        else:
            winner = 0

        ms.match_result_winner = winner
        ms.match_result_reason = None
        ms.phase = 'MATCH_OVER'
        db.session.commit()
        return True

    db.session.commit()
    enter_turn(match)
    return False


# -----------------------------------------------------------------------------
# Timers (kept compatible with your match fields)
# -----------------------------------------------------------------------------

def check_timeout(match: Match) -> bool:
    if not match.is_waiting_decision or not match.decision_started_at:
        return False
    timeout = ROUND_RESULT_TIMEOUT if match.decision_type == 'NEXT' else DECISION_TIMEOUT
    return (time.time() - match.decision_started_at) > timeout


def set_decision_timer(match: Match, decision_type: str) -> None:
    match.decision_started_at = time.time()
    match.decision_type = decision_type
    match.is_waiting_decision = True


def clear_decision_timer(match: Match) -> None:
    match.decision_started_at = None
    match.decision_type = None
    match.is_waiting_decision = False


def get_timer_remaining(match: Match) -> Optional[float]:
    if not match.is_waiting_decision or not match.decision_started_at:
        return None
    timeout = ROUND_RESULT_TIMEOUT if match.decision_type == 'NEXT' else DECISION_TIMEOUT
    remaining = timeout - (time.time() - match.decision_started_at)
    return max(0, remaining)


def apply_timeout(match: Match) -> bool:
    """
    Apply default action for current phase.
    Returns True if state changed.
    Safe to call repeatedly in a loop.
    """

    # Only act if a timeout actually occurred
    if not check_timeout(match):
        return False

    ms = _get_match_state(match.id)
    phase = ms.phase

    # 🔐 CRITICAL:
    # Clear the expired timer FIRST to prevent re-trigger loops
    clear_decision_timer(match)
    db.session.commit()

    # ---- CARD_DRAW (no decision required) ----
    if phase == 'CARD_DRAW':
        return False

    # ---- CHOICE ----
    if phase == 'CHOICE':
        make_choice(match, random.choice([True, False]))
        return True

    # ---- WAITING_BETS ----
    if phase == 'WAITING_BETS':
        turn_index = int(ms.current_turn)
        t = _get_turn(match.id, turn_index)

        if int(t.chips) > 0:
            place_bets(match, [1])
        else:
            end_turn(match)

        return True

    # ---- INSURANCE ----
    if phase == 'INSURANCE':
        turn_index = int(ms.current_turn)
        rnd = _get_active_round(match.id, turn_index)
        if not rnd:
            return False

        round_index = int(rnd.round_index)
        hands = (
            MatchHand.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index
            )
            .order_by(MatchHand.box_index.asc(), MatchHand.hand_index.asc())
            .all()
        )

        handle_insurance(match, [False] * len(hands))
        return True

    # ---- PLAYER TURN ----
    if phase == 'PLAYER_TURN':
        player_action(match, 'stand')
        return True

    # ---- JOKER CHOICE ----
    if phase == 'JOKER_CHOICE':
        turn_index = int(ms.current_turn)
        rnd = _get_active_round(match.id, turn_index)

        if not rnd:
            return False

        round_index = int(rnd.round_index)
        bi = int(rnd.current_box)
        hi = int(rnd.current_hand)

        seqs = _unassigned_joker_seqs_for_hand(
            match.id, turn_index, round_index, bi, hi
        )

        # Auto-assign Ace (11)
        for seq in seqs:
            row = MatchHandCard.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                box_index=bi,
                hand_index=hi,
                seq=seq
            ).first()
            if row:
                row.joker_chosen_value = 11

        db.session.commit()

        # Reuse normal evaluation flow
        assign_joker_values(match, ["A"] * len(seqs))
        return True

    # ---- DEALER JOKER CHOICE ----
    if phase == 'DEALER_JOKER_CHOICE':
        turn_index = int(ms.current_turn)
        rnd = _get_active_round(match.id, turn_index)

        if not rnd:
            return False

        round_index = int(rnd.round_index)

        seqs = _unassigned_joker_seqs_for_dealer(
            match.id, turn_index, round_index
        )

        # Auto-assign Ace (11)
        for seq in seqs:
            row = MatchDealerCard.query.filter_by(
                match_id=match.id,
                turn_index=turn_index,
                round_index=round_index,
                seq=seq
            ).first()
            if row:
                row.joker_chosen_value = 11

        db.session.commit()

        assign_dealer_joker_values(match, ["A"] * len(seqs))
        return True

    # ---- DEALER TURN ----
    if phase == 'DEALER_TURN':
        dealer_action(match, 'stand')
        return True

    # ---- ROUND RESULT (5 second visibility rule) ----
    if phase == 'ROUND_RESULT':
        next_round_or_end_turn(match)
        return True

    return False

# -----------------------------------------------------------------------------
# Client state builder (assembled from SQL rows)
# -----------------------------------------------------------------------------

def get_client_state(match: Match, user_player_num: int, spectator: bool = False) -> Dict[str, Any]:
    ms = _get_match_state(match.id)

    cs: Dict[str, Any] = {
        'current_turn': int(ms.current_turn),
        'phase': ms.phase,
        'match_over': bool(ms.match_over),
        'is_heads_up': bool(ms.is_heads_up),
        'draw_winner': ms.draw_winner,
        'chooser': ms.chooser,
        'choice_made': bool(ms.choice_made),
        'draw_timestamp': ms.draw_timestamp,
        'game_mode': match.game_mode,
        'results': {},
        'match_result': None,
        'total_turns': MatchTurn.query.filter_by(match_id=match.id).count() or 4,
    }

    # timer info from match row (if your routes include it)
    cs['timer_remaining'] = get_timer_remaining(match)
    cs['decision_type'] = match.decision_type

    # draw cards
    draw_rows = (
        MatchDrawCard.query.filter_by(match_id=match.id)
        .order_by(MatchDrawCard.player_num.asc(), MatchDrawCard.seq.asc())
        .all()
    )
    draw_cards = {'player1': [], 'player2': []}
    for r in draw_rows:
        key = 'player1' if int(r.player_num) == 1 else 'player2'
        draw_cards[key].append(_codes_to_card(r.rank_code, r.suit_code))
    cs['draw_cards'] = draw_cards

    # results map
    res_rows = (
        MatchTurnResult.query.filter_by(match_id=match.id)
        .order_by(MatchTurnResult.player_num.asc(), MatchTurnResult.turn_number.asc())
        .all()
    )
    for rr in res_rows:
        cs['results'][f"player{int(rr.player_num)}_turn{int(rr.turn_number)}"] = int(rr.chips_end)

    if ms.match_result_winner is not None or ms.match_result_reason is not None:
        cs['match_result'] = {
            'winner': ms.match_result_winner,
            'reason': ms.match_result_reason,
        }

    # current turn roles
    turns = (
        MatchTurn.query.filter_by(match_id=match.id)
        .order_by(MatchTurn.turn_index.asc())
        .all()
    )
    if turns and int(ms.current_turn) < len(turns):
        t = turns[int(ms.current_turn)]
        cs['current_player_role'] = int(t.player_role)
        cs['current_dealer_role'] = int(t.dealer_role)

        if spectator:
            cs['i_am_dealer'] = False
            cs['is_my_turn'] = False
            cs['is_dealer_turn'] = ms.phase in ('DEALER_TURN', 'DEALER_JOKER_CHOICE')
        else:
            if ms.phase in ('DEALER_TURN', 'DEALER_JOKER_CHOICE'):
                cs['i_am_dealer'] = (int(t.dealer_role) == user_player_num)
                cs['is_my_turn'] = (int(t.dealer_role) == user_player_num)
                cs['is_dealer_turn'] = True
            elif ms.phase in ('CARD_DRAW', 'CHOICE'):
                cs['i_am_dealer'] = (int(t.dealer_role) == user_player_num)
                cs['is_my_turn'] = (ms.phase != 'CHOICE') or (int(ms.chooser or 0) == user_player_num)
                cs['is_dealer_turn'] = False
            else:
                cs['i_am_dealer'] = (int(t.dealer_role) == user_player_num)
                cs['is_my_turn'] = (int(t.player_role) == user_player_num)
                cs['is_dealer_turn'] = False

        # chips
        cs['chips'] = int(t.chips)
        cs['starting_chips'] = int(t.starting_chips)

        # round
        if t.active_round_index is not None:
            rnd = MatchRound.query.filter_by(match_id=match.id, turn_index=int(t.turn_index), round_index=int(t.active_round_index)).first()
            if rnd:
                round_index = int(rnd.round_index)

                show_all_dealer = bool(rnd.resolved) or ms.phase in ('DEALER_TURN', 'DEALER_JOKER_CHOICE')
                is_dealer = (int(t.dealer_role) == user_player_num) and (not spectator)

                dealer = _dealer_cards(match.id, int(t.turn_index), round_index)
                if show_all_dealer or is_dealer:
                    dealer_cards_view = dealer
                else:
                    dealer_cards_view = [dealer[0], {'rank': '?', 'suit': '?'}] if dealer else []

                cs['round'] = {
                    'dealer_cards': dealer_cards_view,
                    'dealer_value': hand_value(dealer) if (show_all_dealer or is_dealer) else (hand_value([dealer[0]]) if dealer else 0),
                    'current_box': int(rnd.current_box),
                    'current_hand': int(rnd.current_hand),
                    'insurance_offered': bool(rnd.insurance_offered),
                    'resolved': bool(rnd.resolved),
                    'boxes': [],
                }

                boxes = (
                    MatchBox.query.filter_by(match_id=match.id, turn_index=int(t.turn_index), round_index=round_index)
                    .order_by(MatchBox.box_index.asc())
                    .all()
                )
                for b in boxes:
                    bi = int(b.box_index)
                    hands = (
                        MatchHand.query.filter_by(match_id=match.id, turn_index=int(t.turn_index), round_index=round_index, box_index=bi)
                        .order_by(MatchHand.hand_index.asc())
                        .all()
                    )
                    box_data = {'hands': []}
                    for h in hands:
                        hi = int(h.hand_index)
                        cards = _hand_cards(match.id, int(t.turn_index), round_index, bi, hi)
                        hv = hand_value(cards)

                        can_split = False
                        can_double = False
                        if h.status == 'active':
                            can_split = _can_split(cards, int(t.chips), int(h.bet))
                            can_double = _can_double(cards, int(t.chips), int(h.bet))

                        box_data['hands'].append({
                            'cards': cards,
                            'bet': int(h.bet),
                            'status': h.status,
                            'result': h.result,
                            'is_split': bool(h.is_split),
                            'is_doubled': bool(h.is_doubled),
                            'value': hv,
                            'can_split': can_split,
                            'can_double': can_double,
                            'has_unassigned_jokers': _has_unassigned_jokers(cards),
                        })
                    cs['round']['boxes'].append(box_data)

    # joker prompts
    if ms.phase == 'JOKER_CHOICE':
        turn_index = int(ms.current_turn)
        rnd = _get_active_round(match.id, turn_index)
        if rnd:
            round_index = int(rnd.round_index)
            bi = int(rnd.current_box)
            hi = int(rnd.current_hand)
            cs['joker_choice'] = {
                'box': bi,
                'hand': hi,
                'indices': _unassigned_joker_seqs_for_hand(match.id, turn_index, round_index, bi, hi),
            }

    if ms.phase == 'DEALER_JOKER_CHOICE':
        turn_index = int(ms.current_turn)
        rnd = _get_active_round(match.id, turn_index)
        if rnd:
            round_index = int(rnd.round_index)
            cs['dealer_joker_indices'] = _unassigned_joker_seqs_for_dealer(match.id, turn_index, round_index)

    return cs
