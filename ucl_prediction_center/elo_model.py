"""Online Elo plus a training-only fitted Davidson draw model."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax
class EloState:
    def __init__(self): self.ratings = {}
    def rating(self, team): return self.ratings.get(team, 1500.0)
    def update(self, home, away, hg, ag, advantage=1.0):
        h, a = self.rating(home), self.rating(away)
        expected = 1 / (1 + 10 ** (-(h - a + 60 * advantage) / 400))
        actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        delta = 20 * (actual - expected)
        self.ratings[home], self.ratings[away] = h + delta, a - delta

class EloModel:
    def fit(self, X, y):
        d = X['ELO_DIFF'].to_numpy() + 60 * X['HOME_ADVANTAGE'].to_numpy()
        def probabilities(theta):
            z = np.clip(d / (400 * np.exp(theta[0])), -10, 10)
            return softmax(np.column_stack([z, np.full(len(z), theta[1]), -z]), axis=1)
        def loss(theta):
            p = probabilities(theta)
            return -np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)).mean() + 0.001 * np.square(theta).sum()
        result = minimize(loss, [0.0, -0.5], bounds=[(-2, 2), (-4, 2)], method='L-BFGS-B')
        if not result.success: raise ValueError('Elo probability calibration did not converge: ' + result.message)
        self.theta = result.x
        return self
    def predict_proba(self, X):
        z = np.clip((X['ELO_DIFF'].to_numpy() + 60 * X['HOME_ADVANTAGE'].to_numpy()) / (400 * np.exp(self.theta[0])), -10, 10)
        return softmax(np.column_stack([z, np.full(len(z), self.theta[1]), -z]), axis=1)
