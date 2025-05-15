import random

def ai_decision_engine(market_data):
    # Простейшая логика ИИ для трейдинга
    volatility = market_data.get('volatility', 0)
    change = market_data.get('change', 0)
    volume = market_data.get('volume', 0)
    pattern = market_data.get('candle_pattern', None)

    if abs(change) >= 4 and volatility >= 2 and volume >= 50_000_000:
        if pattern == 'bullish_engulfing':
            return {'action': 'BUY', 'sl': 0.98, 'tp': 1.03, 'confidence': 0.9, 'reason': 'Bullish pattern + high volatility'}
        elif pattern == 'bearish_engulfing':
            return {'action': 'SELL', 'sl': 1.02, 'tp': 0.97, 'confidence': 0.9, 'reason': 'Bearish pattern + high volatility'}
        else:
            return {'action': 'BUY', 'sl': 0.98, 'tp': 1.03, 'confidence': 0.75, 'reason': 'Volatility + Volume OK'}
    return {'action': 'HOLD', 'confidence': 0.5, 'reason': 'No signal'}
