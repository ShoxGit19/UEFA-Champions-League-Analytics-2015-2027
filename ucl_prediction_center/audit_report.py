"""Human-readable metrics, complete JSON reports and a calibration figure."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [clean(v) for v in value]
    if isinstance(value,(datetime_type(),pd.Timestamp,Path)): return str(value)
    if isinstance(value,np.ndarray): return clean(value.tolist())
    if isinstance(value,np.generic): return clean(value.item())
    if isinstance(value,float) and not np.isfinite(value): return None
    return value

def datetime_type():
    from datetime import datetime
    return datetime

def save_json(path,value): path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def write_reports(directory,audit,validation,backtest,predictions,calibration=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    save_json(directory/'model_audit.json',audit);save_json(directory/'data_validation.json',validation)
    save_json(directory/'backtest_metrics.json',backtest);save_json(directory/'predictions.json',predictions.to_dict('records'))
    lines=['# UCL Prediction Center - Model Report','',f'Model: **{audit["model_name"]}**',f'UTC cutoff: {audit["training_cutoff"]}',
       f'Training matches: {audit["training_matches"]}; selected fixtures: {len(predictions)}','',audit['model_selection_reason'],'',
       '## Chronological validation','', '| Model | Matches | Log loss | Brier | Accuracy | ECE | Goal MAE | Exact top 1 | Exact top 3 |',
       '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for n,m in backtest.get('validation',{}).items():
        lines.append(f'| {n} | {m["n_matches"]} | {m["log_loss"]:.4f} | {m["brier_score"]:.4f} | {m["accuracy"]:.3f} | {m["calibration_error"]:.4f} | {m["goal_mae"]:.3f} | {m["exact_score_top_1_accuracy"]:.3f} | {m["exact_score_top_3_accuracy"]:.3f} |')
    if backtest.get('test'):
        lines+=['','## Untouched chronological test','', '```json',json.dumps(backtest['test']['selected_metrics'],indent=2),'```']
    lines+=['','## Data quality','',f'Rejected rows: {validation["rejected_rows"]}. All row dispositions and individual issues are in data_validation.json.','']
    lines += ['- '+w for w in audit['data_quality_warnings']]
    lines += ['','## Interpretation','',
       'Exact-score probabilities come from two regularized Poisson goal regressions. Their 0-10 joint matrix is normalized. If the selected outcome model differs, H/D/A regions are rescaled to that model; relative score probabilities inside each region stay unchanged. All markets and expected goals use this final matrix.',
       'The 0-10 grid conditions on scores within that range; omitted tail mass is not represented. Goal rates are bounded to 0.05-6 for extrapolation stability.',
       'Confidence is an explicit data-quality heuristic, not the probability that a prediction is correct. LOW_DATA predictions use smoothing and must be interpreted cautiously.',
       'Results are conditional on workbook accuracy. Historical results and future fixtures have not been verified against an external football provider. No regulation/extra-time distinction is available.',
       'The Power BI visual is display-only. Refresh Excel data in Power BI after running the external model.']
    (directory/'model_report.md').write_text('\n'.join(lines),encoding='utf-8')
    if calibration:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        p=np.array(calibration['probabilities']); y=np.array(calibration['targets'])
        fig,ax=plt.subplots(figsize=(7,5));ax.plot([0,1],[0,1],'--',color='gray')
        for cls,label in enumerate(['Home','Draw','Away']):
            x=[];observed=[]
            for low in np.linspace(0,.9,10):
                mask=(p[:,cls]>=low)&(p[:,cls]<low+.1+1e-12)
                if mask.any():x.append(p[mask,cls].mean());observed.append((y[mask]==cls).mean())
            ax.plot(x,observed,'o-',label=label)
        ax.set(xlabel='Predicted probability',ylabel='Observed frequency',title='Held-out test calibration',xlim=(0,1),ylim=(0,1));ax.legend();fig.tight_layout();fig.savefig(directory/'calibration.png',dpi=150);plt.close(fig)
