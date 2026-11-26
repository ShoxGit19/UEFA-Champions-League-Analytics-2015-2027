"""Badge rendering is tested without any network dependency."""
import base64
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox
import numpy as np
import pandas as pd
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import power_bi_visual as visual

def image_bytes(format='PNG'):
    buf=BytesIO();Image.new('RGB',(60,90),(240,140,20)).save(buf,format=format);return buf.getvalue()

def fixture(**extra):
    row=dict(MATCH_ID='m1',DATE_TIME='2026-10-20T21:00:00Z',HOME_TEAM='Home',AWAY_TEAM='Away',
        HOME_WIN_PROB=.5,DRAW_PROB=.3,AWAY_WIN_PROB=.2,PREDICTED_HOME_GOALS=2,PREDICTED_AWAY_GOALS=1,
        EXPECTED_HOME_GOALS=1.8,EXPECTED_AWAY_GOALS=1.1,EXACT_SCORE_PROB=.12,MODEL_CONFIDENCE=.7,MODEL_STATUS='READY')
    row.update(extra);return row

class LogoVisualTests(unittest.TestCase):
    def tearDown(self):
        plt.close('all');visual.load_logo.cache_clear()
    def test_existing_and_new_logo_columns_both_supported(self):
        row=pd.Series({'HOME_TEAM_LOGO':None,'HOME_LOGO_URL':'https://example.test/home.png',
            'AWAY_TEAM_LOGO':'https://example.test/away.png'})
        self.assertEqual(visual.logo_sources(row,'HOME'),['https://example.test/home.png'])
        self.assertEqual(visual.logo_sources(row,'AWAY'),['https://example.test/away.png'])
    def test_data_uri_and_raw_base64_png_jpeg(self):
        for fmt in ['PNG','JPEG']:
            encoded=base64.b64encode(image_bytes(fmt)).decode()
            for source in [encoded,'data:image/'+fmt.lower()+';base64,'+encoded]:
                with self.subTest(format=fmt,uri=source.startswith('data:')):
                    image=visual.load_logo(source);self.assertEqual(image.shape,(100,100,4))
    def test_actual_images_added_for_both_teams(self):
        data_uri='data:image/png;base64,'+base64.b64encode(image_bytes()).decode()
        fig=visual.render_predictions(pd.DataFrame([fixture(HOME_LOGO_BASE64=data_uri,AWAY_LOGO_BASE64=data_uri)]),logo_directory='missing')
        self.assertEqual(fig.ucl_logo_diagnostics['rendered'],2)
        self.assertEqual(sum(isinstance(a,AnnotationBbox) for a in fig.axes[0].artists),2)
        fig.canvas.draw()
    def test_existing_url_basename_uses_local_photo_without_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'Club Name.png').write_bytes(image_bytes())
            names,stems=visual.photo_index(tmp)
            with patch.object(visual,'urlopen',side_effect=AssertionError('Network must not be called')):
                image=visual.resolve_logo('Club',['https://example.test/Club_Name.png'],names,stems)
                self.assertIsNotNone(image)
    def test_svg_url_uses_existing_manchester_city_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'Manchester_City_F.C.-Logo.wine_new.png').write_bytes(image_bytes())
            names,stems=visual.photo_index(tmp)
            with patch.object(visual,'urlopen',side_effect=AssertionError('SVG URL must not be requested')):
                self.assertIsNotNone(visual.resolve_logo('Manchester City',['https://example.test/Manchester_City_FC_badge.svg'],names,stems))
    def test_corrupt_or_missing_logos_do_not_hide_forecasts(self):
        fig=visual.render_predictions(pd.DataFrame([fixture(HOME_LOGO_BASE64='data:image/png;base64,broken')]),logo_directory='missing',logo_resolver=lambda team,sources:None)
        self.assertEqual(fig.ucl_logo_diagnostics['missing_teams'],['Away','Home'])
        texts=[cell.get_text().get_text() for cell in fig.axes[0].tables[0].get_celld().values()]
        self.assertIn('Home',texts);self.assertIn('50%',texts);self.assertIn('2-1',texts)
    def test_null_model_status_falls_back_to_prediction_status(self):
        row=fixture(MODEL_STATUS=pd.NA,PREDICTION_STATUS='LOW_DATA')
        fig=visual.render_predictions(pd.DataFrame([row]),logo_directory='missing',logo_resolver=lambda team,sources:None)
        fig.canvas.draw()
        texts=[cell.get_text().get_text() for cell in fig.axes[0].tables[0].get_celld().values()]
        self.assertIn('LOW_DATA',texts)
    def test_infinite_and_noninteger_scores_display_unavailable(self):
        for value in [float('inf'),float('-inf'),pd.NA,1.5,-1]:
            with self.subTest(value=value):
                self.assertEqual(visual.predicted_score(pd.Series(fixture(PREDICTED_HOME_GOALS=value))),'N/A')
        self.assertEqual(visual.predicted_score(pd.Series(fixture())),'2-1')
    def test_infinite_probabilities_display_unavailable(self):
        self.assertEqual(visual.number(pd.Series({'HOME_WIN_PROB':float('inf')}),'HOME_WIN_PROB',True),'N/A')
    def test_invalid_url_does_not_prevent_local_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'Home.png').write_bytes(image_bytes())
            names,stems=visual.photo_index(tmp)
            image=visual.resolve_logo('Home',['https://[invalid/logo.png'],names,stems)
            self.assertIsNotNone(image)
    def test_invalid_url_without_local_badge_does_not_crash(self):
        self.assertIsNone(visual.resolve_logo('Missing',['https://[invalid/logo.png'],{},{}))
    def test_truncated_http_response_is_handled(self):
        from http.client import IncompleteRead
        with patch.object(visual,'urlopen',side_effect=IncompleteRead(b'incomplete')):
            self.assertIsNone(visual.load_logo('https://example.test/truncated.png'))
    def test_invalid_bytes_return_none(self):
        self.assertIsNone(visual.decode_image(b'not an image'))
    def test_unreachable_url_does_not_crash_visual(self):
        with patch.object(visual,'urlopen',side_effect=OSError('offline')):
            self.assertIsNone(visual.load_logo('https://example.test/unreachable.png'))
    def test_no_future_fixture_rows_created(self):
        fig=visual.render_predictions(pd.DataFrame(columns=['MATCH_ID','DATE_TIME']),logo_directory='missing')
        self.assertEqual(fig.ucl_logo_diagnostics['requested'],0);self.assertFalse(fig.axes[0].tables)

if __name__=='__main__':unittest.main()
