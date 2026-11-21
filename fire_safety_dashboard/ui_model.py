"""Pure presentation helpers. Safety decisions remain in app_v2.evaluate_safety."""
import time


def sensor_presentation(slot, threshold, decimals=0, now=None, stale_after=15):
    now = time.time() if now is None else now
    value, timestamp = slot['value'], slot['timestamp']
    if value is None or timestamp is None:
        return dict(value='--', freshness='Menunggu data', tone='muted', progress=0)
    age = max(0, now - timestamp)
    if age > stale_after:
        return dict(value='--', freshness='Data kedaluwarsa', tone='muted', progress=0)
    progress = max(0, min(value / threshold, 1)) if threshold else 0
    tone = 'danger' if value >= threshold else 'warning' if value >= threshold * .6 else 'safe'
    return dict(value=f'{value:.{decimals}f}',
                freshness='Baru diperbarui' if age < 1 else f'Diperbarui {int(age)} dtk lalu',
                tone=tone, progress=progress)
