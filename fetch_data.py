#!/usr/bin/env python3
"""
Brett Baty Fan Club 2026 — Fantrax Data Fetcher
Runs via GitHub Actions 4x daily to update league_data.json
"""
import json, os, time, sys
from datetime import datetime
try:
    import requests
except ImportError:
    os.system('pip install requests')
    import requests

LEAGUE_ID = 'n25i1grumg7kg722'
BASE_URL = f'https://www.fantrax.com/fxpa/req?leagueId={LEAGUE_ID}'
SESSION_COOKIE = os.environ.get('FANTRAX_COOKIES', '')

def fantrax_post(method, data=None):
    """Make a POST request to the Fantrax API"""
    if not data:
        data = {}
    data['leagueId'] = LEAGUE_ID
    payload = {'msgs': [{'method': method, 'data': data}]}
    headers = {
        'Content-Type': 'application/json',
        'Cookie': f'session={SESSION_COOKIE}' if SESSION_COOKIE else '',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get('pageError'):
            print(f'API Error for {method}: {result["pageError"]["text"]}')
            return None
        return result.get('responses', [{}])[0].get('data')
    except Exception as e:
        print(f'Request failed for {method}: {e}')
        return None

def get_standings():
    """Fetch combined standings"""
    data = fantrax_post('getStandings', {'view': 'COMBINED'})
    if not data:
        return []
    teams = []
    team_info = data.get('fantasyTeamInfo', {})
    tables = data.get('tables', [])
    # Find main standings table
    for table in tables:
        if table.get('tableType') == 'H2hRecord':
            for row in table.get('rows', []):
                fixed = row.get('fixedCells', [])
                cells = row.get('cells', [])
                if len(fixed) >= 2 and len(cells) >= 9:
                    team_id = fixed[1].get('teamId', '')
                    info = team_info.get(team_id, {})
                    team = {
                        'id': team_id,
                        'name': info.get('name', fixed[1].get('content', '')),
                        'short': info.get('shortName', ''),
                        'rank': int(fixed[0].get('content', 0)),
                        'w': int(cells[0].get('content', 0)),
                        'l': int(cells[1].get('content', 0)),
                        't': int(cells[2].get('content', 0)),
                        'winPct': float(cells[3].get('content', '0').replace(',', '')),
                        'div': cells[4].get('content', ''),
                        'gb': cells[5].get('content', '0'),
                        'ww': int(cells[6].get('content', 0)),
                        'pf': float(cells[7].get('content', '0').replace(',', '')),
                        'pa': float(cells[8].get('content', '0').replace(',', '')),
                        'streak': cells[9].get('content', '') if len(cells) > 9 else ''
                    }
                    teams.append(team)
            break
    return teams

def get_season_stats():
    """Fetch season stats"""
    data = fantrax_post('getStandings', {'view': 'SEASON_STATS'})
    if not data:
        return {}
    return data

def get_schedule():
    """Fetch schedule/results"""
    data = fantrax_post('getStandings', {'view': 'SCHEDULE'})
    if not data:
        return {}
    return data

def get_transactions(view='TRADE', page=0):
    """Fetch transactions"""
    data = fantrax_post('getTransactions', {
        'view': view,
        'maxResultsPerPage': 100,
        'pageNumber': page
    })
    if not data:
        return []
    return data.get('transactions', [])

def main():
    print(f'Fetching Fantrax data at {datetime.utcnow().isoformat()}')
    
    # Collect all data
    output = {
        'lastUpdated': datetime.utcnow().isoformat() + 'Z',
        'leagueId': LEAGUE_ID,
        'season': 2026,
        'standings': [],
        'seasonStats': {},
        'schedule': {},
        'transactions': [],
        'currentPeriod': None
    }
    
    print('Getting standings...')
    output['standings'] = get_standings()
    print(f'  Got {len(output["standings"])} teams')
    
    time.sleep(1)
    print('Getting season stats...')
    output['seasonStats'] = get_season_stats()
    
    time.sleep(1)
    print('Getting schedule...')
    output['schedule'] = get_schedule()
    
    time.sleep(1)
    print('Getting transactions...')
    txns = get_transactions()
    output['transactions'] = txns[:200] if txns else []
    print(f'  Got {len(output["transactions"])} transactions')
    
    # Save output
    os.makedirs('data', exist_ok=True)
    with open('data/league_data.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print('Saved data/league_data.json')
    
    # Also update last_updated timestamp
    with open('data/last_updated.json', 'w') as f:
        json.dump({'timestamp': output['lastUpdated'], 'period': output.get('currentPeriod')}, f)
    
    print('Done!')

if __name__ == '__main__':
    main()
