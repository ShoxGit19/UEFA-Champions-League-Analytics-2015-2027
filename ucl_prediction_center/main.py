"""External training / Excel update entry point: python main.py."""
import argparse
import importlib.metadata
import sys
from pathlib import Path
import joblib
import pandas as pd
from threadpoolctl import threadpool_limits
from config import Config,VERSION,TITLE,discover_workbook
from workbook_loader import load_source
from schema_mapper import map_matches
from team_normalization import team_catalog
from data_validation import validate
from feature_engineering import build_features
from backtesting import validation_backtest,heldout_test
from model_selection import select_model
from ml_model import ModelBundle
from prediction_engine import predict
from audit_report import write_reports,save_json
from excel_writer import update_workbook,WorkbookLockedError

def run(args):
    here=Path(__file__).resolve().parent
    workbook=Path(args.workbook).resolve() if args.workbook else discover_workbook(here.parent)
    config=Config(workbook,here,source_timezone=args.timezone)
    cutoff=pd.Timestamp.now(tz='UTC')
    print(TITLE,flush=True);print(f'Workbook: {workbook}\nUTC cutoff: {cutoff.isoformat()}',flush=True)
    frames,schema,fingerprint,load_warnings=load_source(workbook)
    matches,mapping,schema_warnings=map_matches(frames['matches'])
    catalog,team_warnings=team_catalog(frames.get('teams'))
    history,upcoming,validation=validate(matches,catalog,cutoff,config)
    print(f'Validated: {len(history)} historical; {validation["upcoming_fixtures"]} upcoming; {validation["rejected_rows"]} rejected. Selecting {len(upcoming)}.',flush=True)
    X,Z,state=build_features(history,upcoming,cutoff,config.completion_lag_hours)
    print(f'Built {len(X.columns)} pre-match features. Running chronological validation...',flush=True)
    report,test_start=validation_backtest(history,X,config)
    selected,reason=select_model(report)
    print(f'Selected: {selected}. {reason}',flush=True)
    calibration=None
    if test_start is not None:
        report['test'],calibration=heldout_test(history,X,test_start,selected,config)
        print('Held-out test: '+str(report['test']['selected_metrics']),flush=True)
    bundle=None
    if len(history)>=config.minimum_training:
        print('Fitting final models on all eligible historical matches...',flush=True)
        bundle=ModelBundle().fit(X,history)
    predictions=predict(upcoming,Z,bundle,selected,report,catalog,cutoff,config)
    warnings=validation['data_quality_warnings']+schema_warnings+team_warnings+load_warnings
    warnings.extend([f'{k}: {v} affected match rows' for k,v in validation['issue_counts'].items()])
    if report['status']!='VALIDATED': warnings.append(report['warning'])
    audit={'title':TITLE,'model_name':selected,'model_version':VERSION,'training_cutoff':cutoff.isoformat(),
       'training_matches':len(history),'upcoming_matches':len(predictions),'source_workbook':str(workbook),
       'source_sha256':fingerprint,'source_timezone':config.source_timezone,'completion_lag_hours':config.completion_lag_hours,
       'schema_mapping':mapping,'workbook_schema':schema,'feature_list':list(X.columns),
       'validation_metrics':report.get('validation',{}),'heldout_test':report.get('test'),
       'model_selection_reason':reason,'data_quality_warnings':warnings,'timestamp':cutoff.isoformat(),
       'prediction_status_counts':predictions.PREDICTION_STATUS.value_counts().to_dict(),
       'excluded_sources':['predictions','season_winners','final_match_team','final_match_player','goals','players','bracket_progression','team UCL_TITLES'],
       'feature_policy':'Pre-match result replay; results available at kickoff + 3 hours. Historical features use only available earlier results; future fixtures use only information observed at current cutoff. Final presumed neutral; source NEUTRAL flag used when present.',
       'prior_policy':'Elo begins at 1500; K=20; home offset=60. Initial goal prior 1.35 per team with ten pseudo-matches; team rates use five pseudo-matches from previously observed league goals. These are modeling priors, not inserted workbook statistics.',
       'confidence_policy':'Equal mean of history coverage, outcome margin, model agreement, 1-validation ECE, feature completeness, multiplied by history coverage (minimum team UCL history / 20, capped at 1). Heuristic, not correctness probability.',
       'goal_policy':'Independent Poisson, 0..10 normalized grid; model outcome reconciliation; no Dixon-Coles correction or blend without validation evidence.',
       'dependency_versions':{m:importlib.metadata.version(m) for m in ['pandas','numpy','scipy','scikit-learn','openpyxl','joblib','matplotlib']}}
    reports=here/'reports';models=here/'models';models.mkdir(exist_ok=True)
    if bundle is not None:
        joblib.dump({'version':VERSION,'selected_model':selected,'bundle':bundle,'feature_state':state,
          'feature_columns':list(X.columns),'cutoff':cutoff,'source_sha256':fingerprint,'audit':audit},models/'ucl_model.joblib')
    write_reports(reports,audit,validation,report,predictions,calibration)
    if args.dry_run:
        print('DRY RUN: source workbook unchanged. Reports and model artifact generated.',flush=True)
    else:
        try:
            result=update_workbook(workbook,predictions,audit,fingerprint)
        except WorkbookLockedError as exc:
            save_json(reports/'excel_write_receipt.json',exc.receipt)
            save_json(reports/'model_audit.json',audit)
            if audit.get('replaced_prediction_formulas'): save_json(reports/'original_prediction_formulas.json',audit['replaced_prediction_formulas'])
            raise
        save_json(reports/'excel_write_receipt.json',result)
        save_json(reports/'model_audit.json',audit)
        if audit.get('replaced_prediction_formulas'): save_json(reports/'original_prediction_formulas.json',audit['replaced_prediction_formulas'])
        print(f'Existing workbook updated: {workbook}; preserved {result["preserved_parts"]} original ZIP parts unchanged. No separate workbook created.',flush=True)
    print(f'Predictions: {len(predictions)}; statuses: {audit["prediction_status_counts"]}\nReports: {reports}',flush=True)
    return 0

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description=TITLE)
    parser.add_argument('--workbook',help='Source .xlsx; default discovers one workbook beside project')
    parser.add_argument('--timezone',default='UTC',help='Timezone for naive workbook kickoffs; owner confirmed UTC')
    parser.add_argument('--dry-run',action='store_true',help='Generate reports/model without modifying Excel')
    args=parser.parse_args()
    try:
        with threadpool_limits(limits=2): return run(args)
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}: {exc}',file=sys.stderr,flush=True)
        import traceback
        traceback.print_exc()
        return 1
if __name__=='__main__': raise SystemExit(main())
