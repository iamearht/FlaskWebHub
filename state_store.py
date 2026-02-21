"""
Normalized SQL-first persistence for Match.game_state.

This module intentionally keeps the existing *in-memory* state shape exactly the
same as engine.py expects. The refactor is storage-only.

Strategy:
- Prefer normalized tables (MatchState + related card/hand/round tables).
- Fallback to legacy Match.game_state JSON if no normalized rows exist.

NOTE: This first cut uses a simple "delete + bulk insert" approach on save for
correctness. It can be optimized later to incremental updates.
"""

from __future__ import annotations

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

RANK_TO_CODE = {r: i for i, r in enumerate(CARD_RANKS)}
CODE_TO_RANK = {i: r for i, r in enumerate(CARD_RANKS)}
SUIT_TO_CODE = {s: i for i, s in enumerate(CARD_SUITS)}
CODE_TO_SUIT = {i: s for i, s in enumerate(CARD_SUITS)}


def _card_to_codes(card: Dict[str, Any]) -> Tuple[int, int, Optional[int]]:
    rank = card.get('rank')
    suit = card.get('suit')
    if rank not in RANK_TO_CODE:
        raise ValueError(f"Unknown rank: {rank}")
    if suit not in SUIT_TO_CODE:
        raise ValueError(f"Unknown suit: {suit}")
    chosen = card.get('chosen_value')
    return RANK_TO_CODE[rank], SUIT_TO_CODE[suit], chosen


def _codes_to_card(rank_code: int, suit_code: int, chosen_value: Optional[int] = None) -> Dict[str, Any]:
    card = {'rank': CODE_TO_RANK[int(rank_code)], 'suit': CODE_TO_SUIT[int(suit_code)]}
    if chosen_value is not None:
        card['chosen_value'] = int(chosen_value)
    return card


def has_normalized_state(match_id: int) -> bool:
    return db.session.query(MatchState.match_id).filter(MatchState.match_id == match_id).first() is not None


def load_match_state(match: Match) -> Dict[str, Any]:
    """Load the engine-compatible state dict from normalized tables, fallback to JSON."""
    if not match or not match.id:
        return match.game_state or {}

    ms: MatchState | None = MatchState.query.filter_by(match_id=match.id).first()
    if not ms:
        # Legacy row
        return match.game_state or {}

    # Base state skeleton
    state: Dict[str, Any] = {
        'phase': ms.phase,
        'game_mode': match.game_mode,
        'is_heads_up': bool(ms.is_heads_up),
        'draw_deck': [],
        'draw_deck_pos': int(ms.draw_deck_pos),
        'draw_cards': {'player1': [], 'player2': []},
        'draw_winner': ms.draw_winner,
        'chooser': ms.chooser,
        'choice_made': bool(ms.choice_made),
        'current_turn': int(ms.current_turn),
        'turns': [],
        'results': {},
        'turn_state': None,
        'match_over': bool(ms.match_over),
        'match_result': None,
        'draw_timestamp': ms.draw_timestamp,
    }

    if ms.match_result_winner is not None or ms.match_result_reason is not None:
        state['match_result'] = {
            'winner': ms.match_result_winner,
            'reason': ms.match_result_reason,
        }

    # Draw deck
    deck_rows = (
        MatchDrawDeckCard.query.filter_by(match_id=match.id)
        .order_by(MatchDrawDeckCard.pos.asc())
        .all()
    )
    state['draw_deck'] = [_codes_to_card(r.rank_code, r.suit_code) for r in deck_rows]

    # Draw cards
    draw_rows = (
        MatchDrawCard.query.filter_by(match_id=match.id)
        .order_by(MatchDrawCard.player_num.asc(), MatchDrawCard.seq.asc())
        .all()
    )
    for r in draw_rows:
        key = 'player1' if r.player_num == 1 else 'player2'
        state['draw_cards'][key].append(_codes_to_card(r.rank_code, r.suit_code))

    # Turns
    turn_rows = (
        MatchTurn.query.filter_by(match_id=match.id)
        .order_by(MatchTurn.turn_index.asc())
        .all()
    )
    for t in turn_rows:
        state['turns'].append({'player_role': t.player_role, 'dealer_role': t.dealer_role})

    # Results
    res_rows = (
        MatchTurnResult.query.filter_by(match_id=match.id)
        .order_by(MatchTurnResult.player_num.asc(), MatchTurnResult.turn_number.asc())
        .all()
    )
    # engine expects keys like player1_turn1
    for rr in res_rows:
        key = f"player{rr.player_num}_turn{rr.turn_number}"
        state['results'][key] = rr.chips_end

    # Active turn_state (reconstruct from current_turn)
    cur_turn_idx = int(ms.current_turn)
    cur_turn = next((t for t in turn_rows if int(t.turn_index) == cur_turn_idx), None)
    if cur_turn is None:
        state['turn_state'] = None
        return state

    turn_state: Dict[str, Any] = {
        'player_role': cur_turn.player_role,
        'dealer_role': cur_turn.dealer_role,
        'starting_chips': int(cur_turn.starting_chips),
        'chips': int(cur_turn.chips),
        'deck': [],
        'cards_dealt': int(cur_turn.cards_dealt),
        'cut_card_reached': bool(cur_turn.cut_card_reached),
        'round': None,
    }

    deck_rows = (
        MatchTurnDeckCard.query.filter_by(match_id=match.id, turn_index=cur_turn_idx)
        .order_by(MatchTurnDeckCard.pos.asc())
        .all()
    )
    turn_state['deck'] = [_codes_to_card(r.rank_code, r.suit_code) for r in deck_rows]

    if cur_turn.active_round_index is None:
        state['turn_state'] = turn_state
        return state

    cur_round_idx = int(cur_turn.active_round_index)
    rnd = MatchRound.query.filter_by(match_id=match.id, turn_index=cur_turn_idx, round_index=cur_round_idx).first()
    if not rnd:
        state['turn_state'] = turn_state
        return state

    round_state: Dict[str, Any] = {
        'dealer_cards': [],
        'boxes': [],
        'current_box': int(rnd.current_box),
        'current_hand': int(rnd.current_hand),
        'insurance_offered': bool(rnd.insurance_offered),
        'insurance': [],
        'total_initial_bet': int(rnd.total_initial_bet),
    }

    dealer_rows = (
        MatchDealerCard.query.filter_by(match_id=match.id, turn_index=cur_turn_idx, round_index=cur_round_idx)
        .order_by(MatchDealerCard.seq.asc())
        .all()
    )
    round_state['dealer_cards'] = [
        _codes_to_card(r.rank_code, r.suit_code, r.joker_chosen_value) for r in dealer_rows
    ]

    # Boxes -> Hands -> Cards
    box_rows = (
        MatchBox.query.filter_by(match_id=match.id, turn_index=cur_turn_idx, round_index=cur_round_idx)
        .order_by(MatchBox.box_index.asc())
        .all()
    )
    for b in box_rows:
        box_state = {'bet': int(b.bet), 'hands': []}
        hand_rows = (
            MatchHand.query.filter_by(
                match_id=match.id,
                turn_index=cur_turn_idx,
                round_index=cur_round_idx,
                box_index=int(b.box_index),
            )
            .order_by(MatchHand.hand_index.asc())
            .all()
        )
        for h in hand_rows:
            hand_state = {
                'cards': [],
                'bet': int(h.bet),
                'status': h.status,
                'is_split': bool(h.is_split),
                'is_doubled': bool(h.is_doubled),
                'result': h.result,
                'from_split_aces': bool(h.from_split_aces),
                'from_split_jokers': bool(h.from_split_jokers),
            }
            card_rows = (
                MatchHandCard.query.filter_by(
                    match_id=match.id,
                    turn_index=cur_turn_idx,
                    round_index=cur_round_idx,
                    box_index=int(b.box_index),
                    hand_index=int(h.hand_index),
                )
                .order_by(MatchHandCard.seq.asc())
                .all()
            )
            hand_state['cards'] = [
                _codes_to_card(c.rank_code, c.suit_code, c.joker_chosen_value) for c in card_rows
            ]
            box_state['hands'].append(hand_state)

            ins = MatchHandInsurance.query.filter_by(
                match_id=match.id,
                turn_index=cur_turn_idx,
                round_index=cur_round_idx,
                box_index=int(b.box_index),
                hand_index=int(h.hand_index),
            ).first()
            if ins:
                round_state['insurance'].append({
                    'offered': bool(ins.offered),
                    'taken': bool(ins.taken),
                    'amount': int(ins.amount),
                    'decided': bool(ins.decided),
                })
            else:
                round_state['insurance'].append({'offered': False, 'taken': False, 'amount': 0, 'decided': False})

        round_state['boxes'].append(box_state)

    turn_state['round'] = round_state
    state['turn_state'] = turn_state
    return state


def save_match_state(match: Match, state: Dict[str, Any]) -> None:
    """Persist engine-compatible state dict into normalized tables."""
    if not match or not match.id:
        raise ValueError('match must be persisted before saving state')

    # Clear existing normalized rows for match (simple, correct)
    _purge_match_state(match.id)

    # MatchState
    mr = state.get('match_result') or {}
    ms = MatchState(
        match_id=match.id,
        phase=state.get('phase') or 'CARD_DRAW',
        is_heads_up=bool(state.get('is_heads_up', False)),
        draw_deck_pos=int(state.get('draw_deck_pos') or 0),
        draw_winner=state.get('draw_winner'),
        chooser=state.get('chooser'),
        choice_made=bool(state.get('choice_made', False)),
        draw_timestamp=state.get('draw_timestamp'),
        current_turn=int(state.get('current_turn') or 0),
        match_over=bool(state.get('match_over', False)),
        match_result_winner=mr.get('winner'),
        match_result_reason=mr.get('reason'),
    )
    db.session.add(ms)

    # Draw deck
    deck = state.get('draw_deck') or []
    db.session.bulk_save_objects([
        MatchDrawDeckCard(match_id=match.id, pos=i, rank_code=_card_to_codes(c)[0], suit_code=_card_to_codes(c)[1])
        for i, c in enumerate(deck)
    ])

    # Draw cards
    draw_cards = state.get('draw_cards') or {'player1': [], 'player2': []}
    objs: List[MatchDrawCard] = []
    for pnum, key in [(1, 'player1'), (2, 'player2')]:
        for i, c in enumerate(draw_cards.get(key) or []):
            r, s, _ = _card_to_codes(c)
            objs.append(MatchDrawCard(match_id=match.id, player_num=pnum, seq=i, rank_code=r, suit_code=s))
    if objs:
        db.session.bulk_save_objects(objs)

    # Turns (roles)
    turns = state.get('turns') or []
    turn_objs: List[MatchTurn] = []
    for i, t in enumerate(turns):
        turn_objs.append(MatchTurn(
            match_id=match.id,
            turn_index=i,
            player_role=int(t.get('player_role') or 1),
            dealer_role=int(t.get('dealer_role') or 2),
            starting_chips=100,
            chips=100,
            cards_dealt=0,
            cut_card_reached=False,
            active_round_index=None,
        ))
    if turn_objs:
        db.session.bulk_save_objects(turn_objs)
        db.session.flush()

    # Results
    results = state.get('results') or {}
    res_objs: List[MatchTurnResult] = []
    for key, chips_end in results.items():
        # keys: player1_turn1
        if chips_end is None:
            continue
        try:
            p = 1 if key.startswith('player1_') else 2
            tn = int(key.split('turn')[-1])
        except Exception:
            continue
        res_objs.append(MatchTurnResult(match_id=match.id, player_num=p, turn_number=tn, chips_end=int(chips_end)))
    if res_objs:
        db.session.bulk_save_objects(res_objs)

    # Active turn_state
    ts = state.get('turn_state')
    if ts is not None:
        cur_turn_idx = int(state.get('current_turn') or 0)
        # Update the corresponding MatchTurn row
        trow = MatchTurn.query.filter_by(match_id=match.id, turn_index=cur_turn_idx).first()
        if trow:
            trow.starting_chips = int(ts.get('starting_chips') or 100)
            trow.chips = int(ts.get('chips') or 100)
            trow.cards_dealt = int(ts.get('cards_dealt') or 0)
            trow.cut_card_reached = bool(ts.get('cut_card_reached', False))

        # Turn deck
        tdeck = ts.get('deck') or []
        deck_objs: List[MatchTurnDeckCard] = []
        for i, c in enumerate(tdeck):
            r, s, _ = _card_to_codes(c)
            deck_objs.append(MatchTurnDeckCard(match_id=match.id, turn_index=cur_turn_idx, pos=i, rank_code=r, suit_code=s))
        if deck_objs:
            db.session.bulk_save_objects(deck_objs)

        rnd = ts.get('round')
        if rnd is not None:
            # Determine round index for persistence.
            # engine doesn't store it explicitly, so infer from active_round_index if present.
            active_round_index = 0
            if trow and trow.active_round_index is not None:
                active_round_index = int(trow.active_round_index)
            else:
                # Default: current active round is 0
                active_round_index = 0
                if trow:
                    trow.active_round_index = active_round_index

            db.session.add(MatchRound(
                match_id=match.id,
                turn_index=cur_turn_idx,
                round_index=active_round_index,
                current_box=int(rnd.get('current_box') or 0),
                current_hand=int(rnd.get('current_hand') or 0),
                insurance_offered=bool(rnd.get('insurance_offered', False)),
                total_initial_bet=int(rnd.get('total_initial_bet') or 0),
                resolved=False,
            ))

            # Dealer cards
            dealer_cards = rnd.get('dealer_cards') or []
            dealer_objs: List[MatchDealerCard] = []
            for i, c in enumerate(dealer_cards):
                r, s, chosen = _card_to_codes(c)
                dealer_objs.append(MatchDealerCard(
                    match_id=match.id,
                    turn_index=cur_turn_idx,
                    round_index=active_round_index,
                    seq=i,
                    rank_code=r,
                    suit_code=s,
                    joker_chosen_value=chosen,
                ))
            if dealer_objs:
                db.session.bulk_save_objects(dealer_objs)

            boxes = rnd.get('boxes') or []
            insurance_arr = rnd.get('insurance') or []
            for bidx, box in enumerate(boxes):
                bet = int(box.get('bet') or 0)
                db.session.add(MatchBox(
                    match_id=match.id,
                    turn_index=cur_turn_idx,
                    round_index=active_round_index,
                    box_index=bidx,
                    bet=bet,
                ))

                hands = box.get('hands') or []
                for hidx, hand in enumerate(hands):
                    db.session.add(MatchHand(
                        match_id=match.id,
                        turn_index=cur_turn_idx,
                        round_index=active_round_index,
                        box_index=bidx,
                        hand_index=hidx,
                        bet=int(hand.get('bet') or 0),
                        status=hand.get('status') or 'active',
                        is_split=bool(hand.get('is_split', False)),
                        is_doubled=bool(hand.get('is_doubled', False)),
                        result=hand.get('result'),
                        from_split_aces=bool(hand.get('from_split_aces', False)),
                        from_split_jokers=bool(hand.get('from_split_jokers', False)),
                    ))

                    cards = hand.get('cards') or []
                    hcard_objs: List[MatchHandCard] = []
                    for cidx, c in enumerate(cards):
                        r, s, chosen = _card_to_codes(c)
                        hcard_objs.append(MatchHandCard(
                            match_id=match.id,
                            turn_index=cur_turn_idx,
                            round_index=active_round_index,
                            box_index=bidx,
                            hand_index=hidx,
                            seq=cidx,
                            rank_code=r,
                            suit_code=s,
                            joker_chosen_value=chosen,
                        ))
                    if hcard_objs:
                        db.session.bulk_save_objects(hcard_objs)

                    # insurance aligned by hand order globally (as engine stores)
                    ins_data = insurance_arr.pop(0) if insurance_arr else None
                    if ins_data:
                        db.session.add(MatchHandInsurance(
                            match_id=match.id,
                            turn_index=cur_turn_idx,
                            round_index=active_round_index,
                            box_index=bidx,
                            hand_index=hidx,
                            offered=bool(ins_data.get('offered', False)),
                            taken=bool(ins_data.get('taken', False)),
                            amount=int(ins_data.get('amount') or 0),
                            decided=bool(ins_data.get('decided', False)),
                        ))
                    else:
                        db.session.add(MatchHandInsurance(
                            match_id=match.id,
                            turn_index=cur_turn_idx,
                            round_index=active_round_index,
                            box_index=bidx,
                            hand_index=hidx,
                            offered=False,
                            taken=False,
                            amount=0,
                            decided=False,
                        ))


def _purge_match_state(match_id: int) -> None:
    """Delete all normalized state rows for a match."""
    # Delete children first (no ON DELETE CASCADE in all DBs)
    for model in (
        MatchHandInsurance,
        MatchHandCard,
        MatchHand,
        MatchBox,
        MatchDealerCard,
        MatchRound,
        MatchTurnDeckCard,
        MatchTurn,
        MatchDrawCard,
        MatchDrawDeckCard,
        MatchTurnResult,
        MatchState,
    ):
        db.session.query(model).filter_by(match_id=match_id).delete(synchronize_session=False)
