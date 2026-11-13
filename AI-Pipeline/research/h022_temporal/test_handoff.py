"""No-fit tests for the matched comparison and fail-closed launcher."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import experiment
import launch


class HandoffTests(unittest.TestCase):
    def test_threshold(self):
        y=[1]*10+[0]*4
        p=[.9]*9+[.1]+[.2]*4
        self.assertEqual(experiment.threshold(y,p,'early_stop'),.9)
        with self.assertRaises(ValueError):
            experiment.threshold(y,p,'outer_eval')
        with self.assertRaises(ValueError):
            experiment.threshold(y,p[:-1]+[float('nan')],'early_stop')

    def test_own_fold_threshold(self):
        rows=[dict(y=y,baseline=s,temporal=s,baseline_threshold=t,temporal_threshold=t)
              for y,s,t in [(0,.6,.7),(1,.65,.6),(0,.2,.3),(1,.3,.25)]]
        m=experiment.summarize(rows)['temporal']
        self.assertEqual((m['TP'],m['TN'],m['FP'],m['FN']),(2,2,0,0))

    def test_launch_guards(self):
        with patch('launch.sha',return_value=launch.SOURCE_MACHINE):
            with self.assertRaisesRegex(RuntimeError,'preparation laptop'):
                launch.destination_guard()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'manifest'):
                launch.verify_private(root)

    def test_embedding_leakage(self):
        class Example:
            roles={'a':'fit','b':'outer_eval'}
            fold=1
            records={p:[dict(subject_group=p,label='Absent')] for p in ('a','b')}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'table.csv'
            pd.DataFrame([dict(participant_id=p,label='Absent',fold=1,
                               **dict.fromkeys(experiment.FEATURES,0.)) for p in ['a','b']]).to_csv(path,index=False)
            with self.assertRaisesRegex(ValueError,'role mismatch'):
                experiment.embeddings(path,Example(),['fit'])


if __name__=='__main__':
    unittest.main()
