import random
import math
import time

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11
}
CUT_CARD_POSITION = 65
TURN_STARTING_CHIPS = 100
DECISION_TIMEOUT = 10


def create_deck():
    deck = []
    for _ in range(2):
        for suit in SUITS:
            for rank in RANKS:
                deck.append({'rank': rank, 'suit': suit})
    random.shuffle(deck)
    return deck


def hand_value(cards):
    total = 0
    aces = 0
    for c in cards:
        total += CARD_VALUES[c['rank']]
        if c['rank'] == 'A':
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards) == 21


def is_ten_value(rank):
    return rank in ('10', 'J', 'Q', 'K')


def can_split(hand, chips):
    cards = hand['cards']
    if len(cards) != 2 or hand.get('is_split'):
        return False
    r1, r2 = cards[0]['rank'], cards[1]['rank']
    return (r1 == r2 or (is_ten_value(r1) and is_ten_value(r2))) and chips >= hand['bet']


def can_double(hand, chips):
    return len(hand['cards']) == 2 and chips >= hand['bet']


def init_game_state():
    return {
        'current_turn': 0,
        'turns': [
            {'player_role': 1, 'dealer_role': 2},
            {'player_role': 2, 'dealer_role': 1},
        ],
        'results': {'player1': None, 'player2': None},
        'turn_state': None,
        'phase': 'TURN_START',
        'match_over': False,
        'match_result': None,
    }


def enter_turn(state):
    state['turn_state'] = {
        'player_role': state['turns'][state['current_turn']]['player_role'],
        'dealer_role': state['turns'][state['current_turn']]['dealer_role'],
        'deck': create_deck(),
        'cards_dealt': 0,
        'chips': TURN_STARTING_CHIPS,
        'cut_card_reached': False,
        'round': None,
    }
    state['phase'] = 'WAITING_BETS'
    return state


def enter_betting(state):
    state['phase'] = 'WAITING_BETS'
    state['turn_state']['round'] = None
    return state


def place_bets(state, bets):
    ts = state['turn_state']
    if state['phase'] != 'WAITING_BETS':
        return state, 'Not in betting phase'
    if not bets or len(bets) < 1 or len(bets) > 3:
        return state, 'Must place 1-3 bets'

    total_bet = 0
    valid_bets = []
    for b in bets:
        amt = int(b)
        if amt < 1:
            return state, 'Minimum bet per box is 1'
        total_bet += amt
        valid_bets.append(amt)

    if total_bet > ts['chips']:
        return state, 'Total bet exceeds available chips'

    ts['chips'] -= total_bet

    boxes = []
    for bet_amt in valid_bets:
        boxes.append({
            'bet': bet_amt,
            'hands': [{
                'cards': [], 'bet': bet_amt, 'status': 'active',
                'is_split': False, 'is_doubled': False, 'result': None,
            }],
        })

    deck = ts['deck']
    dealt = ts['cards_dealt']
    for box in boxes:
        h = box['hands'][0]
        h['cards'].append(deck[dealt]); dealt += 1
        h['cards'].append(deck[dealt]); dealt += 1

    dealer_cards = [deck[dealt], deck[dealt + 1]]
    dealt += 2
    ts['cards_dealt'] = dealt
    if dealt >= CUT_CARD_POSITION:
        ts['cut_card_reached'] = True

    ts['round'] = {
        'boxes': boxes,
        'dealer_cards': dealer_cards,
        'current_box': 0,
        'current_hand': 0,
        'insurance_offered': False,
        'insurance_taken': False,
        'insurance_amount': 0,
        'total_initial_bet': total_bet,
        'resolved': False,
    }

    if dealer_cards[0]['rank'] == 'A':
        ts['round']['insurance_offered'] = True
        state['phase'] = 'INSURANCE'
    elif is_ten_value(dealer_cards[0]['rank']) and is_blackjack(dealer_cards):
        _resolve_dealer_blackjack(state)
    else:
        _mark_player_blackjacks(ts['round'])
        state['phase'] = 'PLAYER_TURN'
        _advance_to_active(state)

    return state, None


def _resolve_dealer_blackjack(state):
    ts = state['turn_state']
    rnd = ts['round']
    for box in rnd['boxes']:
        for hand in box['hands']:
            if is_blackjack(hand['cards']) and not hand.get('is_split'):
                ts['chips'] += hand['bet']
                hand['status'] = 'push'
                hand['result'] = 'push'
            else:
                hand['status'] = 'lose'
                hand['result'] = 'lose'
    rnd['resolved'] = True
    state['phase'] = 'ROUND_RESULT'


def _mark_player_blackjacks(rnd):
    for box in rnd['boxes']:
        for hand in box['hands']:
            if is_blackjack(hand['cards']) and not hand.get('is_split'):
                hand['status'] = 'blackjack'


def handle_insurance(state, take_insurance):
    ts = state['turn_state']
    rnd = ts['round']
    if state['phase'] != 'INSURANCE':
        return state, 'Not in insurance phase'

    if take_insurance:
        ins_amount = math.floor(rnd['total_initial_bet'] / 2)
        if ins_amount > ts['chips']:
            ins_amount = ts['chips']
        ts['chips'] -= ins_amount
        rnd['insurance_taken'] = True
        rnd['insurance_amount'] = ins_amount

    if is_blackjack(rnd['dealer_cards']):
        if rnd['insurance_taken']:
            ts['chips'] += rnd['insurance_amount'] * 3
        for box in rnd['boxes']:
            for hand in box['hands']:
                if is_blackjack(hand['cards']):
                    ts['chips'] += hand['bet']
                    hand['status'] = 'push'
                    hand['result'] = 'push'
                else:
                    hand['status'] = 'lose'
                    hand['result'] = 'lose'
        rnd['resolved'] = True
        state['phase'] = 'ROUND_RESULT'
    else:
        _mark_player_blackjacks(rnd)
        state['phase'] = 'PLAYER_TURN'
        _advance_to_active(state)

    return state, None


def _advance_to_active(state):
    ts = state['turn_state']
    rnd = ts['round']
    while rnd['current_box'] < len(rnd['boxes']):
        box = rnd['boxes'][rnd['current_box']]
        while rnd['current_hand'] < len(box['hands']):
            hand = box['hands'][rnd['current_hand']]
            if hand['status'] == 'active':
                return
            rnd['current_hand'] += 1
        rnd['current_box'] += 1
        rnd['current_hand'] = 0
    _play_dealer(state)


def player_action(state, action):
    ts = state['turn_state']
    rnd = ts['round']
    if state['phase'] != 'PLAYER_TURN':
        return state, 'Not in player turn phase'

    box = rnd['boxes'][rnd['current_box']] if rnd['current_box'] < len(rnd['boxes']) else None
    if not box:
        return state, 'No active box'
    hand = box['hands'][rnd['current_hand']] if rnd['current_hand'] < len(box['hands']) else None
    if not hand or hand['status'] != 'active':
        return state, 'No active hand'

    deck = ts['deck']

    if action == 'hit':
        hand['cards'].append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        val = hand_value(hand['cards'])
        if val > 21:
            hand['status'] = 'bust'
            hand['result'] = None
            _next_hand(state)
        elif val == 21:
            hand['status'] = 'stand'
            _next_hand(state)

    elif action == 'stand':
        hand['status'] = 'stand'
        _next_hand(state)

    elif action == 'double':
        if not can_double(hand, ts['chips']):
            return state, 'Cannot double'
        ts['chips'] -= hand['bet']
        hand['bet'] *= 2
        hand['is_doubled'] = True
        hand['cards'].append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        if hand_value(hand['cards']) > 21:
            hand['status'] = 'bust'
        else:
            hand['status'] = 'stand'
        _next_hand(state)

    elif action == 'split':
        if not can_split(hand, ts['chips']):
            return state, 'Cannot split'
        ts['chips'] -= hand['bet']
        card1, card2 = hand['cards'][0], hand['cards'][1]
        hand['cards'] = [card1, deck[ts['cards_dealt']]]
        ts['cards_dealt'] += 1
        new_hand = {
            'cards': [card2, deck[ts['cards_dealt']]],
            'bet': hand['bet'], 'status': 'active',
            'is_split': True, 'is_doubled': False, 'result': None,
        }
        ts['cards_dealt'] += 1
        hand['is_split'] = True
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        box['hands'].insert(rnd['current_hand'] + 1, new_hand)
        if hand_value(hand['cards']) == 21:
            hand['status'] = 'stand'
            _next_hand(state)
    else:
        return state, f'Unknown action: {action}'

    return state, None


def _next_hand(state):
    ts = state['turn_state']
    rnd = ts['round']
    rnd['current_hand'] += 1
    box = rnd['boxes'][rnd['current_box']]
    while rnd['current_hand'] < len(box['hands']):
        hand = box['hands'][rnd['current_hand']]
        if hand['status'] == 'active':
            if hand_value(hand['cards']) == 21:
                hand['status'] = 'stand'
                rnd['current_hand'] += 1
                continue
            return
        rnd['current_hand'] += 1
    rnd['current_box'] += 1
    rnd['current_hand'] = 0
    _advance_to_active(state)


def _play_dealer(state):
    ts = state['turn_state']
    rnd = ts['round']
    deck = ts['deck']
    dc = rnd['dealer_cards']

    any_standing = any(
        h['status'] in ('stand', 'blackjack')
        for box in rnd['boxes'] for h in box['hands']
    )

    if any_standing:
        while hand_value(dc) < 17:
            dc.append(deck[ts['cards_dealt']])
            ts['cards_dealt'] += 1
            if ts['cards_dealt'] >= CUT_CARD_POSITION:
                ts['cut_card_reached'] = True

    dealer_val = hand_value(dc)
    dealer_bust = dealer_val > 21
    dealer_bj = is_blackjack(dc)

    for box in rnd['boxes']:
        for hand in box['hands']:
            if hand['status'] == 'bust':
                hand['result'] = 'lose'
            elif hand['status'] == 'blackjack':
                if dealer_bj:
                    ts['chips'] += hand['bet']
                    hand['result'] = 'push'
                else:
                    ts['chips'] += hand['bet'] + math.floor(3 * hand['bet'] / 2)
                    hand['result'] = 'blackjack_win'
            elif hand['status'] == 'stand':
                pval = hand_value(hand['cards'])
                if dealer_bust or pval > dealer_val:
                    ts['chips'] += hand['bet'] * 2
                    hand['result'] = 'win'
                elif pval == dealer_val:
                    ts['chips'] += hand['bet']
                    hand['result'] = 'push'
                else:
                    hand['result'] = 'lose'
            else:
                hand['result'] = 'lose'

    rnd['resolved'] = True
    state['phase'] = 'ROUND_RESULT'


def next_round_or_end_turn(state):
    ts = state['turn_state']
    if ts['cut_card_reached'] or ts['chips'] <= 0:
        return end_turn(state)
    enter_betting(state)
    return state, False


def end_turn(state):
    ts = state['turn_state']
    turn_chips = ts['chips']
    turn_idx = state['current_turn']
    player_role = state['turns'][turn_idx]['player_role']

    if player_role == 1:
        state['results']['player1'] = turn_chips
    else:
        state['results']['player2'] = turn_chips

    state['current_turn'] += 1

    if state['current_turn'] >= 2:
        state['match_over'] = True
        p1 = state['results']['player1'] if state['results']['player1'] is not None else 0
        p2 = state['results']['player2'] if state['results']['player2'] is not None else 0
        if p1 > p2:
            winner = 1
        elif p2 > p1:
            winner = 2
        else:
            winner = 0
        state['match_result'] = {
            'player1_total': p1,
            'player2_total': p2,
            'winner': winner,
        }
        state['phase'] = 'MATCH_OVER'
        return state, True

    state['turn_state'] = None
    state['phase'] = 'TURN_START'
    return state, False


def check_timeout(match):
    if not match.is_waiting_decision or not match.decision_started_at:
        return False
    return (time.time() - match.decision_started_at) > DECISION_TIMEOUT


def apply_timeout(state, match):
    phase = state['phase']
    ts = state.get('turn_state')

    if phase == 'WAITING_BETS':
        if ts and ts['chips'] > 0:
            state, _ = place_bets(state, [1])
        else:
            state, _ = end_turn(state)
        match.is_waiting_decision = False
        return state, True

    elif phase == 'INSURANCE':
        state, _ = handle_insurance(state, False)
        match.is_waiting_decision = False
        return state, True

    elif phase == 'PLAYER_TURN':
        state, _ = player_action(state, 'stand')
        match.is_waiting_decision = False
        return state, True

    elif phase == 'ROUND_RESULT':
        state, _ = next_round_or_end_turn(state)
        match.is_waiting_decision = False
        return state, True

    return state, False


def set_decision_timer(match, decision_type):
    match.decision_started_at = time.time()
    match.decision_type = decision_type
    match.is_waiting_decision = True


def clear_decision_timer(match):
    match.decision_started_at = None
    match.decision_type = None
    match.is_waiting_decision = False


def get_timer_remaining(match):
    if not match.is_waiting_decision or not match.decision_started_at:
        return None
    remaining = DECISION_TIMEOUT - (time.time() - match.decision_started_at)
    return max(0, remaining)


def get_client_state(state, user_player_num, match=None):
    cs = {
        'current_turn': state['current_turn'],
        'phase': state['phase'],
        'results': state['results'],
        'match_over': state['match_over'],
        'match_result': state['match_result'],
        'total_turns': 2,
    }

    if match:
        cs['timer_remaining'] = get_timer_remaining(match)
        cs['decision_type'] = match.decision_type

    if state['current_turn'] < 2:
        ti = state['turns'][state['current_turn']]
        cs['current_player_role'] = ti['player_role']
        cs['current_dealer_role'] = ti['dealer_role']
        cs['is_my_turn'] = (ti['player_role'] == user_player_num)
    else:
        cs['is_my_turn'] = False
        cs['current_player_role'] = None
        cs['current_dealer_role'] = None

    ts = state.get('turn_state')
    if ts:
        cs['chips'] = ts['chips']
        cs['cut_card_reached'] = ts['cut_card_reached']
        rnd = ts.get('round')
        if rnd:
            cs['round'] = {
                'boxes': [],
                'dealer_cards': [],
                'current_box': rnd['current_box'],
                'current_hand': rnd['current_hand'],
                'insurance_offered': rnd['insurance_offered'],
                'insurance_taken': rnd['insurance_taken'],
                'resolved': rnd['resolved'],
            }
            for box in rnd['boxes']:
                b = {'hands': []}
                for hand in box['hands']:
                    h = {
                        'cards': hand['cards'],
                        'bet': hand['bet'],
                        'status': hand['status'],
                        'is_split': hand.get('is_split', False),
                        'is_doubled': hand.get('is_doubled', False),
                        'value': hand_value(hand['cards']),
                        'result': hand.get('result'),
                        'can_split': can_split(hand, ts['chips']) if hand['status'] == 'active' else False,
                        'can_double': can_double(hand, ts['chips']) if hand['status'] == 'active' else False,
                    }
                    b['hands'].append(h)
                cs['round']['boxes'].append(b)

            dc = rnd['dealer_cards']
            if rnd['resolved']:
                cs['round']['dealer_cards'] = dc
                cs['round']['dealer_value'] = hand_value(dc)
            else:
                cs['round']['dealer_cards'] = [dc[0], {'rank': '?', 'suit': '?'}]
                cs['round']['dealer_value'] = CARD_VALUES.get(dc[0]['rank'], 0)
        else:
            cs['round'] = None
    else:
        cs['chips'] = None
        cs['round'] = None

    return cs
