"""Regularized independent Poisson regressions and normalized 0..10 grid."""
import numpy as np
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
GOAL_FEATURES = ['HOME_RECENT_ATTACK','HOME_RECENT_DEFENSE','AWAY_RECENT_ATTACK','AWAY_RECENT_DEFENSE',
 'HOME_AVG_GOALS_FOR','HOME_AVG_GOALS_AGAINST','AWAY_AVG_GOALS_FOR','AWAY_AVG_GOALS_AGAINST',
 'HOME_VENUE_ATTACK','HOME_VENUE_DEFENSE','AWAY_VENUE_ATTACK','AWAY_VENUE_DEFENSE',
 'ELO_DIFF','HOME_ADVANTAGE','LEAGUE_HOME_GOALS','LEAGUE_AWAY_GOALS','HOME_NEW_TEAM','AWAY_NEW_TEAM']

def normalize_probabilities(p):
    a = np.asarray(p,dtype=float)
    if not np.isfinite(a).all() or (a < 0).any(): raise ValueError('Invalid probabilities')
    total = a.sum(axis=-1,keepdims=True)
    if (total<=0).any(): raise ValueError('Zero probability mass')
    return a/total

def score_matrix(home, away):
    if not np.isfinite([home,away]).all() or min(home,away)<0: raise ValueError('Invalid expected goals')
    matrix = np.outer(poisson.pmf(np.arange(11),home),poisson.pmf(np.arange(11),away))
    if matrix.sum()<=0: raise ValueError('No score mass')
    return matrix/matrix.sum()

def outcome_probabilities(matrix):
    return normalize_probabilities([np.tril(matrix,-1).sum(),np.trace(matrix),np.triu(matrix,1).sum()])

def reconcile_matrix(matrix, probabilities):
    """Scale each H/D/A region to calibrated outcome probabilities, preserving
    Poisson relative score likelihoods inside each region. This makes all markets
    and displayed expected goals consistent with the final joint distribution.
    """
    h,a = np.indices(matrix.shape)
    result = matrix.copy()
    for mask, target in zip([h>a,h==a,h<a],normalize_probabilities(probabilities)):
        mass = result[mask].sum()
        if mass <= 0 and target > 0: raise ValueError('Cannot reconcile zero-mass region')
        result[mask] *= target/mass if mass else 0
    return result/result.sum()

def summarize_matrix(matrix):
    h,a = np.indices(matrix.shape)
    ranked = np.argsort(-matrix.ravel(),kind='stable')[:5]
    top = [(int(i//11),int(i%11),float(matrix.ravel()[i])) for i in ranked]
    return {'probabilities':outcome_probabilities(matrix), 'expected_home':float((matrix*h).sum()),
       'expected_away':float((matrix*a).sum()),'top':top,
       'BOTH_TEAMS_SCORE_PROB':float(matrix[(h>0)&(a>0)].sum()),
       'OVER_2_5_PROB':float(matrix[h+a>=3].sum()),'UNDER_2_5_PROB':float(matrix[h+a<=2].sum()),
       'OVER_3_5_PROB':float(matrix[h+a>=4].sum()),'CLEAN_SHEET_HOME_PROB':float(matrix[:,0].sum()),
       'CLEAN_SHEET_AWAY_PROB':float(matrix[0,:].sum())}

class GoalModel:
    def fit(self, X, home, away):
        self.models = []
        for target in [home,away]:
            pipe = make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),
                                 PoissonRegressor(alpha=1.0,max_iter=1000,tol=1e-7))
            pipe.fit(X[GOAL_FEATURES],target); self.models.append(pipe)
        return self
    def predict_goals(self, X):
        # Bound pathological extrapolation to keep a 0..10 grid meaningful.
        return np.column_stack([np.clip(m.predict(X[GOAL_FEATURES]),0.05,6.0) for m in self.models])
    def predict_matrices(self, X):
        return [score_matrix(h,a) for h,a in self.predict_goals(X)]
