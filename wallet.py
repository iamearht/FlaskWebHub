from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, WalletTransaction
from auth import login_required, get_current_user
from datetime import datetime

wallet_bp = Blueprint('wallet', __name__)


def record_transaction(user_id, tx_type, amount, status='pending', description=None,
                       crypto_address=None, network=None):
    tx = WalletTransaction(
        user_id=user_id,
        type=tx_type,
        amount=amount,
        status=status,
        description=description,
        crypto_address=crypto_address,
        network=network,
    )
    db.session.add(tx)
    return tx


@wallet_bp.route('/wallet')
@login_required
def wallet_page():
    user = get_current_user()
    transactions = WalletTransaction.query.filter_by(user_id=user.id)\
        .order_by(WalletTransaction.created_at.desc()).limit(50).all()
    return render_template('wallet.html', user=user, transactions=transactions)


@wallet_bp.route('/wallet/deposit', methods=['POST'])
@login_required
def deposit():
    user = get_current_user()
    try:
        amount = float(request.form.get('amount', 0))
    except (ValueError, TypeError):
        flash('Invalid amount.', 'error')
        return redirect(url_for('wallet.wallet_page'))

    if amount < 1:
        flash('Minimum deposit is $1.', 'error')
        return redirect(url_for('wallet.wallet_page'))
    if amount > 10000:
        flash('Maximum deposit is $10,000.', 'error')
        return redirect(url_for('wallet.wallet_page'))

    tx = record_transaction(
        user_id=user.id,
        tx_type='deposit',
        amount=amount,
        status='approved',
        description=f'Deposit of ${amount:.2f}',
    )
    user.coins += int(amount)
    tx.processed_at = datetime.utcnow()
    db.session.commit()
    flash(f'Deposited ${amount:.2f} successfully. Balance: {user.coins} coins.', 'success')
    return redirect(url_for('wallet.wallet_page'))


@wallet_bp.route('/wallet/withdraw', methods=['POST'])
@login_required
def withdraw():
    user = get_current_user()
    try:
        amount = float(request.form.get('amount', 0))
    except (ValueError, TypeError):
        flash('Invalid amount.', 'error')
        return redirect(url_for('wallet.wallet_page'))

    crypto_address = request.form.get('crypto_address', '').strip()
    network = request.form.get('network', '').strip()

    if amount < 1:
        flash('Minimum withdrawal is $1.', 'error')
        return redirect(url_for('wallet.wallet_page'))
    if amount > user.coins:
        flash('Insufficient balance.', 'error')
        return redirect(url_for('wallet.wallet_page'))
    if not crypto_address:
        flash('Wallet address is required.', 'error')
        return redirect(url_for('wallet.wallet_page'))
    if not network:
        flash('Blockchain network is required.', 'error')
        return redirect(url_for('wallet.wallet_page'))

    tx = record_transaction(
        user_id=user.id,
        tx_type='withdrawal',
        amount=amount,
        status='pending',
        description=f'Withdrawal of ${amount:.2f} to {crypto_address[:12]}...',
        crypto_address=crypto_address,
        network=network,
    )
    user.coins -= int(amount)
    db.session.commit()
    flash(f'Withdrawal of ${amount:.2f} submitted. It will be processed shortly.', 'success')
    return redirect(url_for('wallet.wallet_page'))


@wallet_bp.route('/api/transactions')
@login_required
def api_transactions():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    txns = WalletTransaction.query.filter_by(user_id=user.id)\
        .order_by(WalletTransaction.created_at.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()
    return jsonify([{
        'id': t.id,
        'type': t.type,
        'amount': t.amount,
        'status': t.status,
        'description': t.description,
        'created_at': t.created_at.isoformat() if t.created_at else None,
    } for t in txns])
