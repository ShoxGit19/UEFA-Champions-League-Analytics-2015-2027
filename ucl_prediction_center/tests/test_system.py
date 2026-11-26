import sys
import unittest
import tempfile
import json
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import numpy as np
import pandas as pd
from openpyxl import Workbook,load_workbook
from openpyxl.worksheet.table import Table,TableStyleInfo
from openpyxl.styles import PatternFill
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import Config,BASE_COLUMNS,OUTPUT_COLUMNS,discover_workbook
from schema_mapper import map_matches
from data_validation import validate,kickoff_utc
from team_normalization import normalize
from feature_engineering import build_features
from poisson_model import score_matrix,outcome_probabilities,reconcile_matrix,summarize_matrix,normalize_probabilities
from prediction_engine import predict,validate_predictions
from workbook_loader import file_hash
from excel_writer import update_workbook,WorkbookLockedError
from model_selection import select_model
from backtesting import validation_backtest

CUTOFF=pd.Timestamp('2026-10-15T00:00:00Z')

def fixture(i,date=None,home='Home',away='Away',h=None,a=None,status=None):
 return {'MATCH_ID':f'm{i:03d}','DATE_TIME':date or '2026-10-20T20:00:00Z','HOME_TEAM':home,'AWAY_TEAM':away,
    'HOME_SCORE':h,'AWAY_SCORE':a,'SEASON':'2026-2027','STADIUM':'Arena','STAGE':'League phase','STATUS':status,'NEUTRAL':None,'_ROW':i+2}

def checked(rows,catalog=None):
 if catalog is None: catalog={normalize(n):{'logo':'url','name':n} for n in ['Home','Away','New']}
 cfg=Config(Path('input.xlsx'),Path('.'))
 return validate(pd.DataFrame(rows),catalog,CUTOFF,cfg)

class ValidationTests(unittest.TestCase):
 def test_exactly_18(self):
  rows=[fixture(i,home=f'Team {i}') for i in range(18)]
  _,f,r=checked(rows);self.assertEqual(len(f),18);self.assertEqual(r['upcoming_fixtures'],18)
 def test_maximum_18(self):
  _,f,r=checked([fixture(i,home=f'Team {i}') for i in range(25)])
  self.assertEqual(len(f),18);self.assertEqual(r['upcoming_fixtures'],25)
 def test_fewer_18(self):self.assertEqual(len(checked([fixture(1),fixture(2,home='New')])[1]),2)
 def test_zero_upcoming(self):
  h,f,_=checked([fixture(1,'2026-10-10',h=1,a=0)]);self.assertTrue(f.empty);self.assertEqual(len(h),1)
 def test_duplicate_id_rejects_all(self):
  _,f,r=checked([fixture(1),fixture(1,home='New')]);self.assertTrue(f.empty);self.assertEqual(r['rejected_rows'],2)
 def test_missing_identifier(self):
  r=fixture(1);r['MATCH_ID']=None;self.assertEqual(checked([r])[2]['issue_counts']['MISSING_MATCH_ID'],1)
 def test_duplicate_fixture(self):
  _,f,r=checked([fixture(1),fixture(2)]);self.assertTrue(f.empty);self.assertEqual(r['issue_counts']['DUPLICATE_FIXTURE'],2)
 def test_missing_teams(self):
  _,f,r=checked([fixture(1,home=None)]);self.assertTrue(f.empty);self.assertIn('MISSING_HOME_TEAM',r['issue_counts'])
 def test_same_team_alias(self):
  _,f,r=checked([fixture(1,home='Inter',away='Inter Milan')]);self.assertTrue(f.empty);self.assertIn('SAME_TEAM',r['issue_counts'])
 def test_invalid_scores(self):
  for score in [-1,'abc',1.2,float('inf')]:
   with self.subTest(score=score):self.assertTrue(checked([fixture(1,'2026-10-01',h=score,a=0)])[0].empty)
 def test_cancelled_postponed_abandoned(self):
  for status in ['cancelled','postponed','abandoned','suspended']:
   with self.subTest(status=status):
    h,f,r=checked([fixture(1,status=status)]);self.assertTrue(h.empty and f.empty);self.assertEqual(r['rejected_rows'],1)
 def test_scheduled_past_scores_do_not_train(self):self.assertTrue(checked([fixture(1,'2026-10-01',h=0,a=0,status='scheduled')])[0].empty)
 def test_missing_scores_do_not_train(self):self.assertTrue(checked([fixture(1,'2026-10-01')])[0].empty)
 def test_completion_lag(self):self.assertTrue(checked([fixture(1,'2026-10-14T23:00:00Z',h=1,a=0)])[0].empty)
 def test_missing_invalid_dates(self):
  for date in ['bad',pd.NaT]:
   r=fixture(1);r['DATE_TIME']=date
   h,f,report=checked([r]);self.assertTrue(h.empty and f.empty);self.assertEqual(report['rejected_rows'],1)
 def test_same_kickoff_tiebreaker(self):
  _,f,_=checked([fixture(3,home='X'),fixture(1),fixture(2,home='New')]);self.assertEqual(f.MATCH_ID.tolist(),['m001','m002','m003'])
 def test_future_results_rejected(self):
  h,f,r=checked([fixture(1,h=5,a=0)]);self.assertTrue(h.empty and f.empty);self.assertIn('FUTURE_MATCH_HAS_SCORES',r['issue_counts'])
 def test_missing_logos(self):
  _,f,r=checked([fixture(1)],{normalize(n):{'name':n,'logo':None} for n in ['Home','Away']})
  self.assertEqual(len(f),1);self.assertIn('MISSING_HOME_LOGO',r['issue_counts'])
 def test_timezone_conversion(self):
  self.assertEqual(kickoff_utc('2026-10-20 23:00:00+02:00'),pd.Timestamp('2026-10-20T21:00:00Z'))
  self.assertEqual(kickoff_utc('2026-10-20 21:00:00','UTC'),pd.Timestamp('2026-10-20T21:00:00Z'))
  self.assertEqual(kickoff_utc(46315.875),pd.Timestamp('2026-10-20T21:00:00Z'))
 def test_schema_alternates(self):
  row={'FIXTURE_ID':'a','KICKOFF':'2026-10-20','HOME':'Home','AWAY':'Away','HOME_GOALS':None,'AWAY_GOALS':None}
  frame,mapping,warnings=map_matches(pd.DataFrame([row]));self.assertEqual(mapping['DATE_TIME'],'KICKOFF');self.assertTrue(frame.HOME_SCORE.isna().all())
 def test_schema_missing_required(self):
  with self.assertRaisesRegex(ValueError,'MATCH_ID'):map_matches(pd.DataFrame({'HOME':[1]}))
 def test_name_aliases(self):
  for a,b in [('Bayern M\u00fcnchen','Bayern Munich'),('PSG','Paris Saint-Germain'),('Manchester City FC','Manchester City'),('Liverpool FC','Liverpool'),('Sporting Lisbon','Sporting CP'),('Inter','Inter Milan'),('Club Brugge','Club Brugge KV')]:
   self.assertEqual(normalize(a),normalize(b))

class ProbabilityTests(unittest.TestCase):
 def test_normalization(self):self.assertTrue(np.allclose(normalize_probabilities([2,3,5]),[.2,.3,.5]))
 def test_matrix_sum(self):
  for h,a in [(0,0),(.05,6),(1.4,1.2),(6,6)]:
   m=score_matrix(h,a);self.assertEqual(m.shape,(11,11));self.assertAlmostEqual(m.sum(),1);self.assertTrue((m>=0).all())
 def test_outcomes(self):
  p=outcome_probabilities(score_matrix(1.4,1.2));self.assertAlmostEqual(p.sum(),1)
 def test_reconciliation(self):
  p=[.25,.5,.25];m=reconcile_matrix(score_matrix(1.5,.9),p);self.assertTrue(np.allclose(outcome_probabilities(m),p));self.assertAlmostEqual(m.sum(),1)
 def test_totals_clean_sheets(self):
  m=score_matrix(1.5,.9);s=summarize_matrix(m);self.assertAlmostEqual(s['OVER_2_5_PROB']+s['UNDER_2_5_PROB'],1)
  self.assertAlmostEqual(s['CLEAN_SHEET_HOME_PROB'],m[:,0].sum());self.assertEqual(len(s['top']),5)
 def test_invalid_probabilities(self):
  for values in [[0,0,0],[-1,1,1],[float('nan'),1,1]]:
   with self.assertRaises(ValueError):normalize_probabilities(values)

class LeakageTests(unittest.TestCase):
 def test_current_score_not_a_feature(self):
  rows=[fixture(1,'2026-10-01',h=1,a=0),fixture(2,'2026-10-03',h=3,a=0)]
  hist,up,_=checked(rows);X,Z,_=build_features(hist,up,CUTOFF)
  hist.loc[0,'HOME_SCORE']=9;changed,_,_=build_features(hist,up,CUTOFF)
  pd.testing.assert_series_equal(X.iloc[0],changed.iloc[0]);self.assertNotEqual(X.iloc[1].HOME_GOALS_FOR_LAST_5,changed.iloc[1].HOME_GOALS_FOR_LAST_5)
 def test_simultaneous_results_not_shared(self):
  rows=[fixture(1,'2026-10-01T20:00:00Z',h=1,a=0),fixture(2,'2026-10-01T20:00:00Z',away='New',h=2,a=1)]
  hist,up,_=checked(rows);X,_,_=build_features(hist,up,CUTOFF);self.assertEqual(X.iloc[1].HOME_MATCHES,0)
 def test_previous_match_still_in_progress(self):
  hist,up,_=checked([fixture(1,'2026-10-01T20:00:00Z',h=1,a=0),fixture(2,'2026-10-01T21:00:00Z',away='New',h=2,a=1)])
  X,_,_=build_features(hist,up,CUTOFF);self.assertEqual(X.iloc[1].HOME_MATCHES,0)
 def test_future_fixture_features_do_not_advance(self):
  hist,up,_=checked([fixture(1,'2026-10-01',h=1,a=0),fixture(2),fixture(3,'2026-11-01')])
  _,Z,_=build_features(hist,up,CUTOFF);self.assertEqual(Z.iloc[0].HOME_MATCHES,Z.iloc[1].HOME_MATCHES)
 def test_feature_fields_exclude_targets(self):
  hist,up,_=checked([fixture(1,'2026-10-01',h=1,a=0)])
  X,_,_=build_features(hist,up,CUTOFF);self.assertFalse(set(['HOME_SCORE','AWAY_SCORE','TARGET','WIN_TEAM','RESULT_STRING'])&set(X.columns))
 def test_selection_does_not_read_test(self):
  report={'validation':{'Poisson':{'log_loss':.9,'calibration_error':.03,'fold_log_loss_std':.01,'goal_mae':1}},'test':{'bad':'ignored'}}
  self.assertEqual(select_model(report)[0],'Poisson')

class FakeBundle:
 def predict_all(self,X):
  m=score_matrix(1.4,1.1);p=np.array([outcome_probabilities(m) for _ in range(len(X))])
  return {'Poisson':p},[m.copy() for _ in range(len(X))]

class PredictionTests(unittest.TestCase):
 def test_new_team_uses_priors_and_low_data(self):
  hist,up,_=checked([fixture(1,'2026-10-01',h=1,a=0),fixture(2,home='New')])
  X,Z,_=build_features(hist,up,CUTOFF)
  catalog={normalize(n):{'logo':'url'} for n in ['Home','Away','New']}
  output=predict(up,Z,FakeBundle(),'Poisson',{'status':'VALIDATED','validation':{'Poisson':{'calibration_error':.03}}},catalog,CUTOFF,Config(Path('x'),Path('.')))
  self.assertEqual(output.iloc[0].MODEL_STATUS,'LOW_DATA');self.assertEqual(output.iloc[0].MODEL_CONFIDENCE,0);self.assertTrue(pd.notna(output.iloc[0].HOME_WIN_PROB))
  self.assertEqual(output.iloc[0].HOME_TEAM,'New');validate_predictions(output)
 def test_unknown_team_unavailable(self):
  hist,up,_=checked([fixture(1,home='Mystery')]);_,Z,_=build_features(hist,up,CUTOFF)
  output=predict(up,Z,None,'Poisson',{'status':'INSUFFICIENT_DATA'},{normalize('Away'):{'logo':'url'}},CUTOFF,Config(Path('x'),Path('.')))
  self.assertEqual(output.iloc[0].MODEL_STATUS,'UNKNOWN_TEAM');self.assertTrue(pd.isna(output.iloc[0].HOME_WIN_PROB))
 def test_empty_predictions_have_headers(self):
  output=predict(pd.DataFrame(),pd.DataFrame(),None,'Poisson',{}, {},CUTOFF,Config(Path('x'),Path('.')))
  self.assertEqual(list(output.columns),OUTPUT_COLUMNS)

class ExcelTests(unittest.TestCase):
 def create_book(self,path,formula=False):
  w=Workbook();w.active.title='matches';w.active.append(['MATCH_ID']);w.active.append(['keep'])
  s=w.create_sheet('teams');s.append(['TEAM_NAME','TEAM_URL']);s.append(['Home','https://example.org/logo'])
  s=w.create_sheet('predictions');s.append(BASE_COLUMNS)
  for i in range(4):s.append([f'old{i}']+[None]*15)
  s['A1'].fill=PatternFill('solid',fgColor='123456');s['B2'].number_format='yyyy-mm-dd hh:mm';s['A2']='=1' if formula else 'old0'
  table=Table(displayName='Predictions',ref='A1:P5');table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);s.add_table(table)
  w.save(path);w.close()
  with ZipFile(path,'a') as archive:archive.writestr('custom/preserved.bin',b'opaque Excel asset')
 def predictions(self):
  row={c:None for c in OUTPUT_COLUMNS};row.update(MATCH_ID='new',DATE_TIME=pd.Timestamp('2026-10-20'),HOME_TEAM='Home',AWAY_TEAM='Away',HOME_WIN_PROB=.5,DRAW_PROB=.3,AWAY_WIN_PROB=.2,MODEL_STATUS='READY',PREDICTION_STATUS='READY',PREDICTION_CREATED_AT=pd.Timestamp('2026-10-15'))
  return pd.DataFrame([row],columns=OUTPUT_COLUMNS)
 def test_excel_updates_existing_file_without_copies_and_repeat(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p);before=p.read_bytes();fingerprint=file_hash(p)
   result=update_workbook(p,self.predictions(),{'model_name':'Poisson','warnings':['sample']},fingerprint)
   self.assertEqual(list(Path(folder).iterdir()),[p])
   self.assertNotIn('backup',result)
   self.assertNotEqual(p.read_bytes(),before)
   with ZipFile(p) as z:self.assertEqual(z.read('custom/preserved.bin'),b'opaque Excel asset')
   with ZipFile(BytesIO(before)) as a,ZipFile(p) as b:
    for name in a.namelist():
     if name not in result['modified_parts']:self.assertEqual(a.read(name),b.read(name))
   w=load_workbook(p);s=w['predictions'];self.assertEqual(s['G2'].value,.5);self.assertIsNone(s['A3'].value);self.assertEqual(s['A1'].fill.fgColor.rgb,'00123456')
   self.assertEqual(s.tables['Predictions'].ref,f'A1:AO2');self.assertEqual(w['teams']['B2'].value,'https://example.org/logo')
   self.assertIsInstance(s.cell(2,36).value,__import__('datetime').datetime);self.assertIn('model_audit',w.sheetnames);w.close()
   update_workbook(p,pd.DataFrame(columns=OUTPUT_COLUMNS),{'model_name':'empty'},file_hash(p))
   self.assertEqual(list(Path(folder).iterdir()),[p])
   w=load_workbook(p);self.assertIsNone(w['predictions']['A2'].value);self.assertEqual(w['predictions'].tables['Predictions'].ref,'A1:AO1');w.close()
 def test_old_prediction_formulas_are_archived_and_replaced(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p)
   w=load_workbook(p);w['predictions']['G2']='=0.9';w['predictions'].tables['Predictions'].tableColumns[6].calculatedColumnFormula=__import__('openpyxl').worksheet.table.TableFormula(attr_text='0.9');w.save(p);w.close()
   audit={};result=update_workbook(p,self.predictions(),audit,file_hash(p))
   self.assertEqual(result['replaced_prediction_formula_count'],1);self.assertEqual(audit['replaced_prediction_formulas'][0]['cell'],'G2')
   w=load_workbook(p);self.assertEqual(w['predictions']['G2'].value,.5);self.assertIsNone(w['predictions'].tables['Predictions'].tableColumns[6].calculatedColumnFormula);w.close()
 def test_locked_source_leaves_no_copies(self):
  from unittest.mock import patch
  original_open=Path.open
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p);before=p.read_bytes()
   def locked_open(path,mode='r',*args,**kwargs):
    if path==p and mode=='r+b':raise PermissionError('simulated Excel lock')
    return original_open(path,mode,*args,**kwargs)
   with patch.object(Path,'open',locked_open):
    with self.assertRaises(WorkbookLockedError) as caught:update_workbook(p,self.predictions(),{},file_hash(p))
   receipt=caught.exception.receipt
   self.assertEqual(receipt['status'],'PENDING_WORKBOOK_LOCK');self.assertNotIn('prepared_workbook',receipt)
   self.assertEqual(p.read_bytes(),before);self.assertEqual(list(Path(folder).iterdir()),[p])
 def test_verification_failure_leaves_original_and_no_copies(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p);before=p.read_bytes()
   with patch('excel_writer.load_workbook',side_effect=ValueError('verification failed')):
    with self.assertRaisesRegex(ValueError,'verification failed'):update_workbook(p,self.predictions(),{},file_hash(p))
   self.assertEqual(p.read_bytes(),before);self.assertEqual(list(Path(folder).iterdir()),[p])
 def test_changes_during_staging_are_preserved(self):
  from unittest.mock import patch
  original_open=Path.open
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p);before=p.read_bytes();edited=before+b'concurrent edit'
   def changed_open(path,mode='r',*args,**kwargs):
    if path==p and mode=='r+b':
     with original_open(path,'wb') as handle:handle.write(edited)
    return original_open(path,mode,*args,**kwargs)
   with patch.object(Path,'open',changed_open):
    with self.assertRaisesRegex(RuntimeError,'changed while staging'):update_workbook(p,self.predictions(),{},file_hash(p))
   self.assertEqual(p.read_bytes(),edited);self.assertEqual(list(Path(folder).iterdir()),[p])
 def test_changed_source_guard(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p)
   with self.assertRaisesRegex(RuntimeError,'changed'):update_workbook(p,self.predictions(),{},'wronghash')
 def test_formula_guard_keeps_original(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'source.xlsx';self.create_book(p,formula=True);before=p.read_bytes()
   with self.assertRaisesRegex(ValueError,'formula'):update_workbook(p,self.predictions(),{},file_hash(p))
   self.assertEqual(p.read_bytes(),before)

if __name__=='__main__':unittest.main()
