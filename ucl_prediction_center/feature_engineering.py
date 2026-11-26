"""Replay completed results only after an explicit availability lag.

Features are computed before enqueueing the current result. Simultaneous matches
and earlier matches still in progress cannot contribute. Future fixture results
are never used; all fixture features reflect the one current prediction cutoff.
"""
from collections import defaultdict
import heapq
import numpy as np
import pandas as pd
from elo_model import EloState

class FeatureState:
    def __init__(self):
        self.records = defaultdict(list)
        self.pairs = defaultdict(list)
        self.elo = EloState()
        self.home_sum = self.away_sum = 0.0
        self.total = 0
    def update(self, row):
        hg, ag = int(row.HOME_SCORE), int(row.AWAY_SCORE)
        hp, ap = (3, 0) if hg > ag else (1, 1) if hg == ag else (0, 3)
        neutral = neutral_indicator(row)
        self.elo.update(row.HOME_KEY, row.AWAY_KEY, hg, ag, 1 - neutral)
        for team, opp, gf, ga, pts, venue in [(row.HOME_KEY,row.AWAY_KEY,hg,ag,hp,'H'),(row.AWAY_KEY,row.HOME_KEY,ag,hg,ap,'A')]:
            record = {'gf':gf,'ga':ga,'points':pts,'venue':venue,'date':row.KICKOFF_UTC,'season':str(row.SEASON)}
            self.records[team].append(record)
            self.pairs[(team,opp)].append(record)
        self.home_sum += hg; self.away_sum += ag; self.total += 1
    def features(self, row):
        # Weak symmetric goal prior (ten pseudo-observations) for the initial replay.
        lh = (self.home_sum + 13.5) / (self.total + 10)
        la = (self.away_sum + 13.5) / (self.total + 10)
        league = (lh + la) / 2
        f = {'LEAGUE_HOME_GOALS':lh,'LEAGUE_AWAY_GOALS':la,
             'HOME_ADVANTAGE':1.0-neutral_indicator(row)}
        for side, team, venue in [('HOME',row.HOME_KEY,'H'),('AWAY',row.AWAY_KEY,'A')]:
            rec = self.records[team]; recent = rec[-5:]; last10 = rec[-10:]
            vr = [r for r in rec if r['venue'] == venue]
            sr = [r for r in rec if r['season'] == str(row.SEASON)]
            def smoothed(items, field, prior=league):
                return (sum(r[field] for r in items) + 5 * prior) / (len(items) + 5)
            values = {'MATCHES':len(rec),'POINTS_LAST_5':sum(r['points'] for r in recent),
                'WINS_LAST_5':sum(r['points']==3 for r in recent),'DRAWS_LAST_5':sum(r['points']==1 for r in recent),
                'LOSSES_LAST_5':sum(r['points']==0 for r in recent),'POINTS_LAST_10':sum(r['points'] for r in last10),
                'GOALS_FOR_LAST_5':sum(r['gf'] for r in recent),'GOALS_AGAINST_LAST_5':sum(r['ga'] for r in recent),
                'AVG_GOALS_FOR':smoothed(rec,'gf'),'AVG_GOALS_AGAINST':smoothed(rec,'ga'),
                'RECENT_ATTACK':smoothed(recent,'gf'),'RECENT_DEFENSE':smoothed(recent,'ga'),
                'VENUE_MATCHES':len(vr),'VENUE_WINS':sum(r['points']==3 for r in vr),
                'VENUE_POINTS':sum(r['points'] for r in vr),'VENUE_GOALS_FOR':sum(r['gf'] for r in vr),
                'VENUE_GOALS_AGAINST':sum(r['ga'] for r in vr),'VENUE_ATTACK':smoothed(vr,'gf'),
                'VENUE_DEFENSE':smoothed(vr,'ga'),'ELO':self.elo.rating(team),
                'REST_DAYS':(row.KICKOFF_UTC-rec[-1]['date']).total_seconds()/86400 if rec else np.nan,
                'SEASON_MATCHES':len(sr),'SEASON_POINTS':sum(r['points'] for r in sr),
                'SEASON_ATTACK':smoothed(sr,'gf'),'NEW_TEAM':int(not rec)}
            f.update({f'{side}_{k}':v for k,v in values.items()})
        pair = self.pairs[(row.HOME_KEY,row.AWAY_KEY)]
        f['H2H_MATCHES'] = len(pair)
        f['H2H_HOME_POINTS_AVG'] = (sum(r['points'] for r in pair)+5*1.35)/(len(pair)+5)
        f['ELO_DIFF'] = f['HOME_ELO']-f['AWAY_ELO']
        f['STAGE_MISSING'] = int(pd.isna(row.STAGE))
        # Stage dummies are deterministic, not learned from future categories.
        stage = str(row.STAGE).casefold()
        for label, term in [('FINAL','final'),('SEMI','semi'),('QUARTER','quarter'),('LEAGUE','league'),('GROUP','group'),('ROUND','round')]:
            f['STAGE_'+label] = int(stage == 'final') if label == 'FINAL' else int(term in stage)
        return f

def neutral_indicator(row):
    if str(row.get('NEUTRAL','')).strip().casefold() in {'true','1','yes'}: return 1.0
    return float(str(row.get('STAGE','')).strip().casefold() == 'final')

def build_features(history, upcoming, cutoff, lag_hours=3):
    state = FeatureState(); pending = []; features = []
    for i, row in history.iterrows():
        while pending and pending[0][0] <= row.KICKOFF_UTC:
            _, _, previous = heapq.heappop(pending); state.update(previous)
        features.append(state.features(row))
        heapq.heappush(pending,(row.KICKOFF_UTC+pd.Timedelta(hours=lag_hours),int(i),row))
    while pending and pending[0][0] <= cutoff:
        _, _, previous = heapq.heappop(pending); state.update(previous)
    future = [state.features(row) for _,row in upcoming.iterrows()]
    X = pd.DataFrame(features)
    Z = pd.DataFrame(future, columns=X.columns) if len(X.columns) else pd.DataFrame(future)
    return X, Z, state
