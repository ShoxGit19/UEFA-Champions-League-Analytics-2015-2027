"""Expanding-window validation and an untouched final 20% test period."""
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, accuracy_score, confusion_matrix, precision_score
from ml_model import ModelBundle
from poisson_model import reconcile_matrix, summarize_matrix

def calibration_error(y,p,bins=10):
    errors=[]
    for cls in range(3):
        err=0.0
        for b in range(bins):
            mask=(p[:,cls]>=b/bins)&((p[:,cls]<(b+1)/bins) if b<bins-1 else (p[:,cls]<=1))
            if mask.any(): err+=mask.mean()*abs((y[mask]==cls).mean()-p[mask,cls].mean())
        errors.append(err)
    return float(np.mean(errors))

def metrics(history, probabilities, matrices):
    y=history.TARGET.to_numpy(dtype=int); p=np.asarray(probabilities)
    predicted=p.argmax(axis=1); onehot=np.eye(3)[y]
    summaries=[summarize_matrix(m) for m in matrices]
    actual=history[['HOME_SCORE','AWAY_SCORE']].to_numpy(dtype=float)
    expected=np.array([[s['expected_home'],s['expected_away']] for s in summaries])
    hits1=[]; hits3=[]
    for (h,a),s in zip(actual,summaries):
        top=[(t[0],t[1]) for t in s['top']]
        hits1.append((h,a)==top[0]); hits3.append((h,a) in top[:3])
    precision=precision_score(y,predicted,labels=[0,1,2],average=None,zero_division=0)
    return {'n_matches':len(y),'log_loss':float(log_loss(y,p,labels=[0,1,2])),
      'brier_score':float(np.square(p-onehot).sum(axis=1).mean()),'accuracy':float(accuracy_score(y,predicted)),
      'calibration_error':calibration_error(y,p),'confusion_matrix':confusion_matrix(y,predicted,labels=[0,1,2]).tolist(),
      'home_win_precision':float(precision[0]),'draw_precision':float(precision[1]),'away_win_precision':float(precision[2]),
      'goal_mae':float(np.abs(expected-actual).mean()),'exact_score_top_1_accuracy':float(np.mean(hits1)),
      'exact_score_top_3_accuracy':float(np.mean(hits3))}

def evaluate_fold(history,X,start,end,lag_hours,minimum_training):
    first=history.iloc[start].KICKOFF_UTC
    training=np.flatnonzero((history.KICKOFF_UTC+pd.Timedelta(hours=lag_hours)<=first).to_numpy())
    if len(training)<minimum_training: raise ValueError('Not enough completed training matches for chronological fold')
    if training.max()>=start: raise AssertionError('Training crosses validation boundary')
    bundle=ModelBundle().fit(X.iloc[training],history.iloc[training])
    probabilities,base_matrices=bundle.predict_all(X.iloc[start:end])
    per_model={}; matrices={}
    for name,p in probabilities.items():
        joint=[reconcile_matrix(m,q) for m,q in zip(base_matrices,p)]
        matrices[name]=joint
        per_model[name]=metrics(history.iloc[start:end],p,joint)
    metadata={'training_matches':len(training),'training_latest_result_available_utc':(history.iloc[training].KICKOFF_UTC.max()+pd.Timedelta(hours=lag_hours)).isoformat(),
      'evaluation_start_utc':first.isoformat(),'evaluation_end_utc':history.iloc[end-1].KICKOFF_UTC.isoformat(),
      'evaluation_matches':end-start,'failures':bundle.failures}
    return per_model,probabilities,matrices,metadata

def validation_backtest(history,X,config):
    n=len(history)
    times=history.KICKOFF_UTC.drop_duplicates().tolist()
    if n<max(config.minimum_training*2,200) or len(times)<10:
        return {'status':'INSUFFICIENT_DATA','validation':{},'folds':[],
                'warning':'At least 200 matches and ten kickoff groups are required for model selection.'},None
    edges=[]
    for fraction in [.5,.6,.7,.8]:
        time=times[min(len(times)-1,int(len(times)*fraction))]
        edges.append(int(np.searchsorted(history.KICKOFF_UTC.to_numpy(),time)))
    if len(set(edges))!=4: raise ValueError('Not enough distinct chronological boundaries')
    collection={}; folds=[]
    for start,end in zip(edges[:-1],edges[1:]):
        score,probs,joints,meta=evaluate_fold(history,X,start,end,config.completion_lag_hours,config.minimum_training)
        folds.append({'window':meta,'models':score})
        for name,p in probs.items():
            bucket=collection.setdefault(name,{'history':[],'probabilities':[],'matrices':[]})
            bucket['history'].append(history.iloc[start:end]); bucket['probabilities'].append(p); bucket['matrices'].extend(joints[name])
    aggregate={}
    for name,bucket in collection.items():
        if len(bucket['history'])!=len(folds): continue
        score=metrics(pd.concat(bucket['history']),np.concatenate(bucket['probabilities']),bucket['matrices'])
        score['fold_log_loss_std']=float(np.std([fold['models'][name]['log_loss'] for fold in folds]))
        aggregate[name]=score
    return {'status':'VALIDATED','validation':aggregate,'folds':folds,'test_start_index':edges[-1],
        'split_protocol':'50% initial history; expanding validation over 50-60%, 60-70%, 70-80% of unique kickoff groups; final 20% held out. Models refit on completed prior matches at each window; online features advance only as prior results become available.',
        'metric_notes':'Class order H,D,A. Brier = mean sum of three squared errors (range 0..2). ECE = mean of classwise 10-bin errors. Goal MAE averages both teams. Goal/score metrics use each candidate outcome-reconciled Poisson matrix.'},edges[-1]

def heldout_test(history,X,start,selected,config):
    values,probabilities,_,meta=evaluate_fold(history,X,start,len(history),config.completion_lag_hours,config.minimum_training)
    p=probabilities[selected]; y=history.iloc[start:].TARGET.to_numpy(dtype=int)
    return {'window':meta,'models':values,'selected_model':selected,'selected_metrics':values[selected],
            'selection_used_test':False}, {'targets':y.tolist(),'probabilities':p.tolist()}
