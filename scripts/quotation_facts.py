"""Validate extracted quotation candidates. No CRM writes or reminder scheduling."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

class QuoteNeedsConfirmation(ValueError):
    pass

def decimal_value(value, name, positive=False):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+)?', value):
        raise QuoteNeedsConfirmation(name + '_invalid_decimal')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise QuoteNeedsConfirmation(name + '_invalid_decimal')
    if not amount.is_finite() or amount < 0 or (positive and amount <= 0):
        raise QuoteNeedsConfirmation(name + '_out_of_range')
    if amount > Decimal('1000000000000'):
        raise QuoteNeedsConfirmation(name + '_out_of_range')
    return amount

def money_text(value):
    return None if value is None else str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def validate(raw):
    if not isinstance(raw, dict) or raw.get('currency') != 'USD':
        raise QuoteNeedsConfirmation('currency_not_verified_USD')
    items = raw.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise QuoteNeedsConfirmation('quotation_items_missing')
    output = []
    subtotals = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('product'), str) or not item['product'].strip():
            raise QuoteNeedsConfirmation('product_missing')
        quantity = decimal_value(item.get('quantity'), 'quantity', positive=True)
        unit_price = decimal_value(item.get('unit_price'), 'unit_price')
        subtotal = decimal_value(item.get('subtotal'), 'subtotal')
        if quantity is not None and quantity != quantity.to_integral_value():
            raise QuoteNeedsConfirmation('piece_quantity_not_integer')
        if quantity is not None and unit_price is not None and subtotal is not None:
            if (quantity * unit_price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != subtotal.quantize(Decimal('.01'), rounding=ROUND_HALF_UP):
                raise QuoteNeedsConfirmation('line_amount_conflict')
        if subtotal is not None and subtotal != subtotal.quantize(Decimal('.01')):
            raise QuoteNeedsConfirmation('subtotal_currency_precision')
        subtotals.append(subtotal)
        output.append({'product': item['product'].strip(), 'model': item.get('model'),
                       'quantity': None if quantity is None else str(quantity),
                       'unit_price': None if unit_price is None else str(unit_price),
                       'subtotal': money_text(subtotal)})
    goods = decimal_value(raw.get('goods_total'), 'goods_total')
    shipping = decimal_value(raw.get('shipping'), 'shipping')
    if goods is not None and all(value is not None for value in subtotals) and goods != sum(subtotals):
        raise QuoteNeedsConfirmation('goods_total_conflict')
    if any(value is not None and value != value.quantize(Decimal('.01')) for value in (goods, shipping)):
        raise QuoteNeedsConfirmation('total_currency_precision')
    return {'currency':'USD', 'items':output, 'goods_total':money_text(goods),
            'quoted_shipping':money_text(shipping),
            'shipping_state':'待人工确认' if shipping is None else '图中列示，仍需核实货代方案',
            'quotation_total':money_text(goods + shipping) if goods is not None and shipping is not None else None,
            'payment_verified':False, 'shipment_verified':False,
            'uncertainties':raw.get('uncertainties')}

def sent_evidence_ready(source, person_id):
    """Recognition alone cannot prove a real send or its procurement attribution."""
    return bool(source.get('direction') == 'outbound' and
                source.get('person_id') == person_id and source.get('occurred_at') and
                source.get('identity_verified') is True and source.get('actual_send_verified') is True and
                source.get('procurement_link_verified') is True and source.get('opportunity_id') and
                source.get('classification') == 'quotation' and source.get('content_hash') and
                source.get('historical_only') is False)
