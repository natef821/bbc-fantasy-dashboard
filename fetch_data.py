#!/usr/bin/env python3
"""Brett Baty Fan Club 2026 — Fantrax Data Fetcher
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
            print(f'  API Error for {method}: {result.get("pageError")}')
            return None
        responses = result.get('responses', [])
        return responses[0].get('data', {}) if responses else None
    except Exception as e:
        print(f'  Request failed for {method}: {e}')
        return None

def normalize_table_list(data):
    """tableList from API can be a list or a dict; always return a list"""
    tl = data.get('tableList')
    if isinstance(tl, dict):
        return list(tl.values())
    return tl or []

def get_standings():
    """Fetch standings including W/L, FP, FPG, WW claims, PBL balance"""
    data = fantrax_post('getStandings', {'view': 'SEASON_STATS'})
    if not data:
        return []
    teams = []
    team_info = data.get('fantasyTeamInfo', {})
    table_list = normalize_table_list(data)
    main_table = next((t for t in table_list if t.get('tableType') == 'PointsBased1'), None)
    if not main_table:
        print('  Warning: PointsBased1 table not found')
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
                'rank': int(fixed[0].get('content', '0') or '0'),
                'fantasyPoints': cells[1].get('content', '').replace(',', '') if len(cells) > 1 else '',
                'fptsPerGame': cells[2].get('content', '') if len(cells) > 2 else '',
                'scoringPeriod': cells[3].get('content', '') if len(cells) > 3 else '',
                'gb': cells[4].get('content', '') if len(cells) > 4 else '',
                'ww': int(str(cells[5].get('content', '0') or '0').replace(',', '').split('.')[0]) if len(cells) > 5 else 0,
                'pbl': float(str(cells[6].get('content', '0') or '0').replace(',', '')) if len(cells) > 6 else 0,
                'hitPts': float(str(cells[7].get('content', '0') or '0').replace(',', '')) if len(cells) > 7 else 0,
                'pitPts': float(str(cells[8].get('content', '0') or '0').replace(',', '')) if len(cells) > 8 else 0,
            }
            teams.append(team)
    return teams

def get_schedule():
    """Fetch schedule - derives H2H W/L/T per team and full matchup history"""
    data = fantrax_post('getStandings', {'view': 'SCHEDULE'})
    if not data:
        return {}
    table_list = normalize_table_list(data)
    team_info = data.get('fantasyTeamInfo', {})
    records = {}
    periods = []
    for table in table_list:
        if not table.get('tableType', '').startswith('H2h'):
            continue
        period_name = table.get('caption', '')
        period_matchups = []
        for row in table.get('rows', []):
            cells = row.get('cells', [])
            if len(cells) < 4:
                continue
            t1_id = cells[0].get('teamId', '')
            t1_name = cells[0].get('content', '')
            t1_pts = float(str(cells[1].get('content', '0')).replace(',', '') or '0')
            t2_id = cells[2].get('teamId', '')
            t2_name = cells[2].get('content', '')
            t2_pts = float(str(cells[3].get('content', '0')).replace(',', '') or '0')
            if not t1_id:
                continue
            for tid, tname in [(t1_id, t1_name), (t2_id, t2_name)]:
                if tid and tid not in records:
                    records[tid] = {'w': 0, 'l': 0, 't': 0, 'pf': 0, 'pa': 0, 'name': tname, 'weeklyPF': []}
            records[t1_id]['pf'] += t1_pts
            records[t1_id]['pa'] += t2_pts
            records[t1_id]['weeklyPF'].append(t1_pts)
            if t2_id:
                records[t2_id]['pf'] += t2_pts
                records[t2_id]['pa'] += t1_pts
                records[t2_id]['weeklyPF'].append(t2_pts)
            if t1_pts > t2_pts:
                t1_won, t2_won = True, False
            elif t2_pts > t1_pts:
                t1_won, t2_won = False, True
            else:
                t1_won = t2_won = None
            if t1_won is True:
                records[t1_id]['w'] += 1
                if t2_id: records[t2_id]['l'] += 1
            elif t1_won is False:
                records[t1_id]['l'] += 1
                if t2_id: records[t2_id]['w'] += 1
            else:
                records[t1_id]['t'] += 1
                if t2_id: records[t2_id]['t'] += 1
            winner_name = t1_name if t1_won else (t2_name if t1_won is False else 'Tie')
            period_matchups.append({
                'team1': t1_name, 'team1Id': t1_id, 'team1Pts': t1_pts,
                'team2': t2_name, 'team2Id': t2_id, 'team2Pts': t2_pts,
                'winner': winner_name
            })
        periods.append({'period': period_name, 'matchups': period_matchups})
    result_records = []
    for tid, rec in records.items():
        info = team_info.get(tid, {})
        rec['teamId'] = tid
        rec['name'] = info.get('name', rec.get('name', ''))
        rec['short'] = info.get('shortName', '')
        rec['logoUrl'] = info.get('logoUrl512', '')
        rec['pf'] = round(rec['pf'], 2)
        rec['pa'] = round(rec['pa'], 2)
        result_records.append(rec)
    return {'records': result_records, 'periods': periods}

def get_season_stats():
    """Fetch season stats tables for category leaders"""
    data = fantrax_post('getStandings', {'view': 'SEASON_STATS'})
    if not data:
        return {}
    team_info = data.get('fantasyTeamInfo', {})
    table_list = normalize_table_list(data)
    categories = []
    for table in table_list:
        ttype = table.get('tableType', '')
        if ttype in ('PointsBased1', 'PointsBased2'):
            continue
        cat_name = table.get('caption', ttype)
        rows_data = []
        for row in table.get('rows', []):
            fixed = row.get('fixedCells', [])
            cells = row.get('cells', [])
            if len(fixed) < 2:
                continue
            team_id = fixed[1].get('teamId', '')
            info = team_info.get(team_id, {})
            rows_data.append({
                'teamId': team_id,
                'name': info.get('name', fixed[1].get('content', '')),
                'short': info.get('shortName', ''),
                'rank': fixed[0].get('content', ''),
                'values': [c.get('content', '') for c in cells]
            })
        if rows_data:
            categories.append({'name': cat_name, 'rows': rows_data})
    return {'categories': categories, 'teamInfo': {
        tid: {'name': v.get('name', ''), 'short': v.get('shortName', ''), 'logoUrl': v.get('logoUrl512', '')}
        for tid, v in team_info.items()
    }}

def get_transactions(tx_type):
    """Fetch recent transactions"""
    data = fantrax_post('getTransactions', {'transactionType': tx_type, 'maxResultsPerPage': 30})
    if not data:
        return []
    transactions = []
    for tx in data.get('transactions', []):
        player_info = tx.get('player', {}) or {}
        transactions.append({
            'displayDate': tx.get('displayDate', 0),
            'teamId': tx.get('teamId', ''),
            'id': tx.get('id', ''),
            'seq': tx.get('seq', 0),
            'desc': tx.get('description', tx.get('desc', '')),
            'player': {
                'name': player_info.get('name', ''),
                'posShortNames': player_info.get('posShortNames', ''),
                'teamShortName': player_info.get('teamShortName', ''),
                'teamName': player_info.get('teamName', ''),
                'headshotUrl': player_info.get('headshotUrl', ''),
                'scorerId': player_info.get('scorerId', ''),
                'posIds': player_info.get('posIds', []),
                'rookie': player_info.get('rookie', False),
                'minorsEligible': player_info.get('minorsEligible', False),
                'icons': player_info.get('icons', []),
            } if player_info else None
        })
    return transactions

def get_rosters():
    """Fetch team rosters including IL status"""
    data = fantrax_post('getTeamRoster', {'statusOrScoringPeriod': 'ALL_ACTIVE'})
    if not data:
        return {}
    rosters = {}
    for team_id, team_data in data.get('rosters', {}).items():
        roster = []
        for player in team_data.get('rosterItems', []):
            p = player.get('player', {}) or {}
            roster.append({
                'name': p.get('name', ''),
                'pos': p.get('posShortNames', ''),
                'team': p.get('teamShortName', ''),
                'status': player.get('status', ''),
                'isOnIL': player.get('isOnIL', False),
                'headshotUrl': p.get('headshotUrl', ''),
            })
        rosters[team_id] = roster
    return rosters

def main():
    print(f'Fetching Fantrax data at {datetime.utcnow().isoformat()}')
    output = {
        'lastUpdated': datetime.utcnow().isoformat() + 'Z',
        'leagueId': LEAGUE_ID,
        'season': 2026,
        'standings': [],
        'schedule': {},
        'seasonStats': {},
        'transactions': [],
        'mlbTransactions': [],
        'rosters': {},
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
    print('Getting season stats (category leaders)...')
    output['seasonStats'] = get_season_stats()
    cats = output['seasonStats'].get('categories', [])
    print(f'  Got {len(cats)} stat categories')
    print('Getting fantasy transactions (waivers/trades)...')
    output['transactions'] = get_transactions('WAIVER_CLAIM')
    print(f'  Got {len(output["transactions"])} waiver transactions')
    print('Getting MLB transactions (IL/recalls)...')
    output['mlbTransactions'] = get_transactions('TRANSACTION')
    print(f'  Got {len(output["mlbTransactions"])} MLB transactions')
    print('Getting team rosters/IL status...')
    try:
        output['rosters'] = get_rosters()
        print(f'  Got {len(output["rosters"])} team rosters')
    except Exception as e:
        print(f'  Rosters fetch failed: {e}')
        output['rosters'] = {}
    os.makedirs('data', exist_ok=True)
    with open('data/league_data.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f'Saved data/league_data.json')
    print(f'  Standings: {len(output["standings"])} teams')
    print(f'  H2H Records: {len(records)} teams')
    print(f'  Periods: {len(sched.get("periods", []))}')

if __name__ == '__main__':
    main()
