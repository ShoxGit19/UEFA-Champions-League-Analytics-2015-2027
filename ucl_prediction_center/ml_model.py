"""Train only on supplied past rows. Boosting's random early split is disabled."""
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from config import MODEL_NAMES
from elo_model import EloModel
from poisson_model import GoalModel, normalize_probabilities, outcome_probabilities

class ModelBundle:
    def fit(self, X, history):
        self.columns = list(X.columns)
        y = history.TARGET.to_numpy(dtype=int)
        self.baseline = (np.bincount(y,minlength=3)+1)/(len(y)+3)
        self.goals = GoalModel().fit(X,history.HOME_SCORE,history.AWAY_SCORE)
        self.models = {'Elo':EloModel().fit(X,y)}
        self.failures = {}
        estimators = {
          'Logistic Regression':make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),LogisticRegression(C=0.1,max_iter=2000,random_state=42)),
          'HistGradientBoostingClassifier':make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,learning_rate=0.05,l2_regularization=10,early_stopping=False,random_state=42))}
        for name, model in estimators.items():
            try:
                if len(np.unique(y))<2: raise ValueError('Fewer than two outcome classes')
                model.fit(X,y); self.models[name]=model
            except (ValueError,RuntimeError) as exc:
                self.failures[name]=str(exc)
        return self
    def predict_all(self,X):
        matrices = self.goals.predict_matrices(X)
        output = {'Historical baseline':np.tile(self.baseline,(len(X),1)),
                  'Poisson':np.array([outcome_probabilities(m) for m in matrices])}
        for name,model in self.models.items():
            p = model.predict_proba(X)
            if name != 'Elo':
                aligned = np.full((len(X),3),1e-12)
                for col, cls in enumerate(model.classes_): aligned[:,int(cls)] = p[:,col]
                p = aligned
            output[name]=normalize_probabilities(p)
        return output, matrices
