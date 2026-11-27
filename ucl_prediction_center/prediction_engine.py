"""Inference consumes an already fitted bundle; never fits on a visual refresh."""
import json
import numpy as np
import pandas as pd
from config import OUTPUT_COLUMNS,VERSION
from poisson_model import reconcile_matrix,summarize_matrix

def confidence_components(features,probabilities,all_probabilities,ece):
    p=np.sort(probabilities)
    coverage=min(1.0,min(features.HOME_MATCHES,features.AWAY_MATCHES)/20)
    agreement=max(0.0,1-float(np.std(np.array(list(all_probabilities.values())),axis=0).mean())*2)
    fields=np.array(features,dtype=float)
    present=1-float(np.isnan(fields).mean())
    components={'history_coverage':coverage,'outcome_separation':float(p[-1]-p[-2]),
        'model_agreement':agreement,'validation_calibration':max(0.0,1-ece) if ece is not None else 0.0,
        'feature_completeness':present}
    # Equal component mean, multiplied by coverage: transparent heuristic, not a
    # calibrated probability of a correct prediction. New teams score zero.
    return float(np.mean(list(components.values()))*coverage),components

def predict(upcoming,features,bundle,selected,report,catalog,cutoff,config):
    if len(upcoming)==0: return pd.DataFrame(columns=OUTPUT_COLUMNS)
    all_p,base_matrices=bundle.predict_all(features) if bundle is not None else ({},[])
    rows=[]
    for i,row in upcoming.iterrows():
        result={c:None for c in OUTPUT_COLUMNS}
        for c in ['MATCH_ID','SEASON','HOME_TEAM','AWAY_TEAM','STADIUM']:
            v=row[c]; result[c]=None if pd.isna(v) else v
        result.update(DATE_TIME=row.KICKOFF_UTC.to_pydatetime().replace(tzinfo=None),MODEL_NAME=selected,
            MODEL_VERSION=VERSION,PREDICTION_CREATED_AT=cutoff.to_pydatetime().replace(tzinfo=None),
            SOURCE_SEASON=row.get('SEASON'),TRAINING_SAMPLE_COUNT=int(report.get('training_sample_count', 0)))
        for side in ['HOME','AWAY']:
            result[f'{side}_TEAM_LOGO']=catalog.get(row[f'{side}_KEY'],{}).get('logo')
        if row.HOME_KEY not in catalog or row.AWAY_KEY not in catalog:
            status='UNKNOWN_TEAM'; result['DATA_COVERAGE']='LOW'
        elif bundle is None or selected not in all_p:
            status='PREDICTION_UNAVAILABLE'; result['DATA_COVERAGE']='LOW'
        else:
            f=features.iloc[i]
            low=min(f.HOME_MATCHES,f.AWAY_MATCHES)<config.coverage_matches or report['status']!='VALIDATED'
            status='LOW_DATA' if low else 'READY'
            result['DATA_COVERAGE']='LOW' if low else 'HIGH' if min(f.HOME_MATCHES,f.AWAY_MATCHES)>=20 else 'MEDIUM'
            joint=reconcile_matrix(base_matrices[i],all_p[selected][i]); summary=summarize_matrix(joint)
            for c,p in zip(['HOME_WIN_PROB','DRAW_PROB','AWAY_WIN_PROB'],summary['probabilities']): result[c]=float(p)
            result.update(EXPECTED_HOME_GOALS=summary['expected_home'],EXPECTED_AWAY_GOALS=summary['expected_away'],
                PREDICTED_HOME_GOALS=summary['top'][0][0],PREDICTED_AWAY_GOALS=summary['top'][0][1],
                EXACT_SCORE_PROB=summary['top'][0][2],SCORE_MATRIX_JSON=json.dumps(joint.tolist(),separators=(',',':')))
            for rank,(h,a,p) in enumerate(summary['top'],1):
                result[f'TOP_SCORE_{rank}']=f'{h}-{a}'; result[f'TOP_SCORE_{rank}_PROB']=p
            for c,v in summary.items():
                if c.endswith('_PROB'): result[c]=v
            ece=report.get('validation',{}).get(selected,{}).get('calibration_error')
            conf,components=confidence_components(f,all_p[selected][i],{n:p[i] for n,p in all_p.items()},ece)
            result['MODEL_CONFIDENCE']=conf; result['CONFIDENCE_COMPONENTS_JSON']=json.dumps(components)
        result['MODEL_STATUS']=result['PREDICTION_STATUS']=status
        rows.append(result)
    output=pd.DataFrame(rows,columns=OUTPUT_COLUMNS)
    validate_predictions(output)
    return output

def validate_predictions(frame):
    if frame.empty: return
    if frame.MATCH_ID.duplicated().any(): raise AssertionError('Duplicate output MATCH_ID')
    ordered=frame.sort_values(['DATE_TIME','MATCH_ID']).MATCH_ID.tolist()
    if ordered!=frame.MATCH_ID.tolist(): raise AssertionError('Fixtures are not sorted')
    for _,row in frame.iterrows():
        if row.PREDICTION_STATUS in {'UNKNOWN_TEAM','PREDICTION_UNAVAILABLE','INVALID_FIXTURE'}:
            if pd.notna(row.HOME_WIN_PROB): raise AssertionError('Unavailable prediction has probabilities')
            continue
        cols=[c for c in frame.columns if c.endswith('_PROB')]+['MODEL_CONFIDENCE']
        values=np.array([row[c] for c in cols],dtype=float)
        if not np.isfinite(values).all() or (values<0).any() or (values>1).any(): raise AssertionError('Invalid probability')
        if abs(row.HOME_WIN_PROB+row.DRAW_PROB+row.AWAY_WIN_PROB-1)>1e-10: raise AssertionError('Outcome probability sum')
        m=np.array(json.loads(row.SCORE_MATRIX_JSON))
        if abs(m.sum()-1)>1e-10: raise AssertionError('Matrix sum')
        if min(row.EXPECTED_HOME_GOALS,row.EXPECTED_AWAY_GOALS)<0: raise AssertionError('Negative expected goals')
        for c in ['PREDICTED_HOME_GOALS','PREDICTED_AWAY_GOALS']:
            if row[c]<0 or row[c]!=int(row[c]): raise AssertionError('Invalid predicted goals')
