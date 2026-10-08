import json

with open('D:\My Assistant\config.json') as f:
    data = json.load(f)

print('=== APP ACTIVITY HISTORY ===')
for entry in data.get('app_activity_history', [])[-5:]:
    print(f"  {entry.get('date')} - {entry.get('app')}: {entry.get('seconds')}s")

print()
print('=== DASHBOARD ACTIVITY HISTORY ===')
for entry in data.get('dashboard_activity_history', [])[-5:]:
    print(f"  {entry.get('timestamp')} - {entry.get('label')}")

print()
print('=== TRACKED WEBSITES ===')
for site in data.get('tracked_websites', []):
    print(f"  {site.get('domain')}: limit {site.get('limit_minutes')}min, used {site.get('used_seconds')}s")

print()
print('=== WATER REMINDER ===')
print(f"  interval: {data.get('water_reminder_interval_minutes')}min")
print(f"  pending: {data.get('water_reminder_pending')}")

print()
print('=== POMODORO ===')
pomodoro = data.get('pomodoro', {})
print(f"  work: {pomodoro.get('work_minutes')}min, break: {pomodoro.get('break_minutes')}min")

print()
print('=== FOCUS MODE ===')
focus = data.get('focus_mode', {})
print(f"  enabled: {focus.get('enabled')}, blocked: {focus.get('blocked_websites')}")