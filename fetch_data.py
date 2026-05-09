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
        'Cookie': SESSION_COOKIE if SESSION_COOKIE else '',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get('pageError'):
            page_err = result.get('pageError', {})
            print(f'API Error for {method}: {page_err}')
            return None
        return result.get('responses', [{}])[0].get('data')
    except Exception as e:
        print(f'Request failed for {method}: {e}')
        return None

def get_standings():
    """Fetch standings from PointsBased1 table (points-based league)"""
    data = fantrax_post('getStandings', {'view': 'SEASON_STATS'})
    if not data:
        return []
    teams = []
    team_info = data.get('fantasyTeamInfo', {})
    table_list = data.get('tableList', [])
    # tableList can be a list or a dict - normalize to iterable
    if isinstance(table_list, dict):
        table_list = list(table_list.values())
    # Find PointsBased1 table (main standings)
    main_table = None
    for table in table_list:
        if table.get('tableType') == 'PointsBased1':
            main_table = table
            break
    if not main_table:
        print('  Warning: PointsBased1 table not found in standings')
        return []
    for row in main_table.get('rows', []):
        fixed = row.get('fixedCells', [])
        cells = row.get('cells', [])
        if len(fixed) >= 2:
            team_id = fixed[1].get('teamId', '')
            info = team_info.get(team_id, {})
            team = {
                'id': team_id,
                'name': info.get('name', fixed[1].get('content', '')),
                'short': info.get('shortName', ''),
                'logoUrl': info.get('logoUrl512', ''),
                'rank': int(fixed[0].get('content', 0) or 0),
                'fantasyPoints': cells[0].get('content', '0').replace(',', '') if len(cells) > 0 else '0',
                'fptsPerGame': cells[2].get('content', '0') if len(cells) > 2 else '0',
                'scoringPeriod': cells[3].get('content', '') if len(cells) > 3 else '',
                'gb': cells[7].get('content', '0') if len(cells) > 7 else '0',
            }
            teams.append(team)
    return teams

def get_schedule():
    """Fetch schedule/results — derives H2H W/L/T per team"""
    data = fantrax_post('getStandings', {'view': 'SCHEDULE'})
    if not data:
        return {}
    table_list = data.get('tableList', [])
    team_info = data.get('fantasyTeamInfo', {})
    # tableList can be a list or a dict - normalize to iterable
    if isinstance(table_list, dict):
        table_list = list(table_list.values())
    # Build W/L/T records from all scoring periods
    records = {}  # teamId -> {w, l, t, pf, pa}
    periods = []
    for table in table_list:
        if table.get('tableType', '').startswith('H2h'):
            period_name = table.get('caption', '')
            period_matchups = []
            for row in table.get('rows', []):
                cells = row.get('cells', [])
                if len(cells) >= 4:
                    t1_id = cells[0].get('teamId', '')
                    t1_pts = float(str(cells[1].get('content', '0')).replace(',', '') or '0')
                    t2_id = cells[2].get('teamId', '')
                    t2_pts = float(str(cells[3].get('content', '0')).replace(',', '') or '0')
                    t1_name = cells[0].get('content', '')
                    t2_name = cells[2].get('content', '')
                    if t1_id:
                        if t1_id not in records:
                            records[t1_id] = {'w': 0, 'l': 0, 't': 0, 'pf': 0.0, 'pa': 0.0, 'name': t1_name}
                        if t2_id not in records:
                            records[t2_id] = {'w': 0, 'l': 0, 't': 0, 'pf': 0.0, 'pa': 0.0, 'name': t2_name}
                        records[t1_id]['pf'] += t1_pts
                        records[t1_id]['pa'] += t2_pts
                        records[t2_id]['pf'] += t2_pts
                        records[t2_id]['pa'] += t1_pts
                        t1_won = cells[1].get('highlight', False)
                        t2_won = cells[3].get('highlight', False)
                        if t1_won and not t2_won:
                            records[t1_id]['w'] += 1
                            records[t2_id]['l'] += 1
                        elif t2_won and not t1_won:
                            records[t2_id]['w'] += 1
                            records[t1_id]['l'] += 1
                        else:
                            records[t1_id]['t'] += 1
                            records[t2_id]['t'] += 1
                    period_matchups.append({
                        'team1': t1_name, 'team1Id': t1_id, 'team1Pts': t1_pts,
                        'team2': t2_name, 'team2Id': t2_id, 'team2Pts': t2_pts,
                        'winner': t1_name if t1_won else (t2_name if t2_won else 'Tie')
                    })
            periods.append({'period': period_name, 'matchups': period_matchups})
    # Enrich records with team info
    for tid, rec in records.items():
        info = team_info.get(tid, {})
        rec['teamId'] = tid
        rec['name'] = info.get('name', rec.get('name', ''))
        rec['short'] = info.get('shortName', '')
        rec['logoUrl'] = info.get('logoUrl512', '')
        pf = rec['pf']
        pa = rec['pa']
        rec['pf'] = round(pf, 2)
        rec['pa'] = round(pa, 2)
    return {'records': list(records.values()), 'periods': periods}

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

    output = {
        'lastUpdated': datetime.utcnow().isoformat() + 'Z',
        'leagueId': LEAGUE_ID,
        'season': 2026,
        'standings': [],
        'schedule': {},
        'transactions': [],
        'currentPeriod': None
    }

    print('Getting standings...')
    output['standings'] = get_standings()
    print(f'  Got {len(output["standings"])} teams')

    print('Getting schedule/H2H records...')
    sched = get_schedule()
    output['schedule'] = sched
    records = sched.get('records', [])
    print(f'  Got {len(records)} team records, {len(sched.get("periods", []))} periods')

    print('Getting transactions...')
    output['transactions'] = get_transactions()
    print(f'  Got {len(output["transactions"])} transactions')

    # Save to file
    os.makedirs('data', exist_ok=True)
    with open('data/league_data.json', 'w') as f:
        json.dump(output, f, indent=2)

    print(f'Saved data/league_data.json')
    print(f'  Standings: {len(output["standings"])} teams')
    print(f'  H2H Records: {len(records)} teams')
    print(f'  Transactions: {len(output["transactions"])} items')
    print(f'  Cookie set: {bool(SESSION_COOKIE)}')
    print('Done!')

if __name__ == '__main__':
    main()
