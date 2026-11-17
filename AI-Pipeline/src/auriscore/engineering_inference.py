"""Explicit hash-bound local engineering inference, with no final model promotion."""
from pathlib import Path
import json

import numpy as np

from .analysis_service import BackendDefinition, BackendOutput
from .model_audit import digest
from .heart_result import analyze_heart, murmur_branch
from .heart_inference import load_keras_model
from .abdomen_inference import BowelWindowScorer


class H022Scorer:
    def __init__(self, item):
        self.item = item
        self.config = json.loads(Path(item['normalization']).read_text())
        self.model = None

    def score(self, audio, rate):
        from .preprocessing import preprocess
        from .segmentation import segment
        from .spectrogram import extract_spectrogram_tensor
        import tensorflow as tf
        if len(audio)/rate < self.config['window_seconds']:
            raise ValueError('H022 requires a complete window')
        if self.model is None:
            model = load_keras_model(Path(self.item['model']))
            self.model = tf.keras.Model(model.input, model.layers[-2].output)
            if tuple(self.model.output.shape[1:]) != (64,):
                raise ValueError('H022 embedding shape mismatch')
        wave = preprocess(audio, rate, self.config)
        windows, features = [], []
        batch = []
        for start, signal, valid in segment(wave, self.config['sample_rate'],
                                           self.config['window_seconds'], self.config['overlap']):
            windows.append(dict(start_s=start/self.config['sample_rate'],
                                end_s=(start+valid)/self.config['sample_rate']))
            batch.append(extract_spectrogram_tensor(signal, self.config))
            if len(batch) == 32:
                features.extend(self.model(np.stack(batch)[...,None],training=False).numpy())
                batch = []
        if batch:
            features.extend(self.model(np.stack(batch)[...,None],training=False).numpy())
        x=np.asarray(features,dtype=np.float32)
        if x.shape != (len(windows),64) or not np.isfinite(x).all():
            raise ValueError('Invalid H022 embedding')
        with np.load(self.item['head'],allow_pickle=False) as h:
            if h['classes'].tolist()!=[0,1] or h['scaler_mean'].shape!=(64,) or h['coef'].shape!=(1,64) or np.any(h['scaler_scale']<=0):
                raise ValueError('Invalid H022 linear head')
            def probability(v):
                logits=((v-h['scaler_mean'])/h['scaler_scale']) @ h['coef'][0]+h['intercept'][0]
                return np.exp(-np.logaddexp(0,-logits))
            scores=probability(x)
            # Preserve original mean-embedding then logistic head for this one recording.
            score=float(probability(x.mean(axis=0)))
        for row,p in zip(windows,scores,strict=True):
            row['score']=float(p)
        duration=len(wave)/self.config['sample_rate']
        return dict(score=score,windows=windows,window_count=len(windows),duration_s=duration,
                    discarded_tail_s=max(0.,duration-windows[-1]['end_s']))


class TestBackend:
    def __init__(self,mode,item):
        self.mode,self.item=mode,item
        for key, expected in item['hashes'].items():
            if digest(Path(item[key])) != expected:
                raise ValueError('Source changed before model loading')
        if mode=='heart':
            self.scorer=H022Scorer(item)
        else:
            metadata=json.loads(Path(item['metadata']).read_text())
            self.scorer=BowelWindowScorer(Path(item['model']),metadata,expected_model_sha256=item['hashes']['model'])

    def analyze(self,audio,rate):
        item=self.item
        threshold=item['threshold']
        if self.mode=='heart':
            result=analyze_heart(audio,rate)
            if not result['quality']['valid']:
                return BackendOutput(result)
            score=self.scorer.score(audio,rate)
            result['murmur']=murmur_branch(score['score'],threshold,item['version'],
                  preprocessing_version='h022-fold1-frozen-normalization',threshold_version='historical-pooled-oof-reference-only')
            result['murmur'].update(score_kind='uncalibrated_sigmoid',probability_is_calibrated=False,
                window_count=score['window_count'],temporal_evidence=dict(version='heart-window-evidence-v1',
                kind='exploratory_window_scores',threshold_scope='recording_reference_only',
                duration_s=score['duration_s'],discarded_tail_s=score['discarded_tail_s'],windows=score['windows']))
            result['usage_scope']='engineering_test_only'
            return BackendOutput(result)
        score=self.scorer.score_windows(audio,rate)
        windows=[dict(w,label='present' if w['score']>=threshold else 'absent') for w in score['windows']]
        count=sum(w['label']=='present' for w in windows)
        activity=dict(target='bowel_sound_activity',inference_unit='window',aggregation='none',
            model_version=item['version'],preprocessing_version='a005-frozen',threshold_version='saved-validation-reference',
            threshold=threshold,score_kind='uncalibrated_sigmoid',probability_is_calibrated=False,window_seconds=5.,
            overlap=.5,windows=windows,window_count=len(windows),active_window_count=count,
            active_window_fraction=count/len(windows),analyzed_duration_s=score['analyzed_duration_s'],
            discarded_tail_s=score['discarded_tail_s'])
        return BackendOutput(dict(schema_version='abdomen-analysis-v1',mode='abdomen',usage_scope='engineering_test_only',
            quality=dict(valid=True,reason=None),activity=activity,bowel_events=None,bowel_rate_per_minute=None,
            bowel_rate_variability=None,pattern_categories=None,
            limitations=['Local engineering test of A005. No validated disease or individual burst boundary claim.']))


class LungTestBackend:
    """Reuse the research frame decoder with one cached, hash-bound Lung model."""

    def __init__(self, item):
        from .lung_preprocessing import validate_config
        for key, expected in item['hashes'].items():
            if digest(Path(item[key])) != expected:
                raise ValueError('Lung source changed before loading')
        self.item = item
        source = json.loads(Path(item['source']).read_text())
        self.config = source['config']
        validate_config(self.config)
        self.evaluation = json.loads(Path(item['evaluation']).read_text())
        thresholds = np.asarray(self.evaluation['thresholds'], dtype=float)
        if (source.get('evaluation_role') != 'development_only'
                or self.evaluation.get('role') != 'development_only'
                or self.evaluation['classes'] != self.config['classes']
                or thresholds.shape != (len(self.config['classes']),)
                or not np.isfinite(thresholds).all() or np.any((thresholds < 0) | (thresholds > 1))):
            raise ValueError('Incompatible research Lung evaluation')
        with np.load(item['normalization'], allow_pickle=False) as data:
            self.mean, self.std = data['mean'].copy(), data['std'].copy()
        self.model = load_keras_model(Path(item['model']))

    def analyze(self, audio, rate):
        from .lung_localization import predict_frames, _result
        from .analysis_service import AnalysisError
        times, scores = predict_frames(audio, rate, self.config, self.mean, self.std, self.model)
        if not len(times):
            raise ValueError('No analyzed Lung frames')
        output = _result(times, scores, self.config, self.evaluation['thresholds'], len(audio) / rate, 0., 0.)
        output['sound_events'] = [{k: e[k] for k in ('label', 'start_s', 'end_s')} for e in output['sound_events']]
        output['phase_intervals'] = [{k: e[k] for k in ('label', 'start_s', 'end_s')} for e in output['phase_intervals']]
        output.update(schema_version='lung-analysis-v1', mode='lung', quality=dict(valid=True, reason=None),
            model_version=self.item['version'], supported_classes=self.config['classes'],
            class_scores=[dict(label=label, maximum_frame_score=float(scores[:, i].max()),
                threshold=self.evaluation['thresholds'][i]) for i, label in enumerate(self.config['classes'])],
            limitations=['L006 local engineering test; device accuracy is unverified.',
                         'Temporal intervals are frame-grid candidates. Scores are uncalibrated.'])
        errors = []
        if output['respiratory']['reason']:
            errors.append(AnalysisError('LUNG_INSUFFICIENT_CYCLES', 'Insufficient unambiguous respiratory cycles.', 'respiratory'))
        return BackendOutput(output, 'partial' if errors else 'completed', errors)


class L030ClipBackend:
    """Score the same complete 62-frame blocks used in L030 development."""

    def __init__(self, folder: Path):
        from .lung_preprocessing import validate_config

        metadata = json.loads((folder / 'config.json').read_text())
        classes = ['wheeze', 'rhonchi', 'crackle']
        if (metadata['experiment'] != 'EXP-L030-frame-temporal-delta'
                or metadata['classes'] != classes or metadata['clip_frames'] != 62
                or metadata['deployment_eligible'] is not False):
            raise ValueError('Invalid L030 engineering metadata')
        for name in ('best_model.keras', 'normalization.npz'):
            if digest(folder / name) != metadata['sha256'][name]:
                raise ValueError('L030 asset hash mismatch')
        self.config = {**metadata['preprocessing'], 'classes': classes}
        validate_config(self.config)
        self.thresholds = np.asarray(metadata['thresholds'], dtype=float)
        if (self.thresholds.shape != (3,) or not np.isfinite(self.thresholds).all()
                or np.any((self.thresholds < 0) | (self.thresholds > 1))):
            raise ValueError('Invalid L030 clip thresholds')
        with np.load(folder / 'normalization.npz', allow_pickle=False) as norm:
            self.mean, self.std = norm['mean'], norm['std']
        if (self.mean.shape != (self.config['n_mels'],) or self.std.shape != self.mean.shape
                or not np.isfinite(self.mean).all() or not np.isfinite(self.std).all()
                or np.any(self.std <= 0)):
            raise ValueError('Invalid L030 normalization')
        self.model = load_keras_model(folder / 'best_model.keras')

    def analyze(self, audio, rate):
        from .analysis_service import AnalysisError
        from .lung_dsp import respiratory_measurements
        from .lung_preprocessing import windows

        config = self.config
        sample_rate, hop, fft = (config[k] for k in ('sample_rate', 'hop_length', 'n_fft'))
        duration = len(audio) / rate
        sample_count = round(duration * sample_rate)
        classes = config['classes']
        maximum = np.zeros(3)
        events = []
        for block in windows(audio, rate, [], config):
            features = np.clip((block['features'] - self.mean) / self.std, -5, 5)
            scores = np.asarray(self.model(features[None], training=False))
            if (scores.shape != (1, len(features), 3) or not np.isfinite(scores).all()
                    or np.any((scores < 0) | (scores > 1))):
                raise ValueError('Invalid L030 frame scores')
            start = block['start_sample']
            for first in range(0, len(features) - 61, 62):
                end = start + (first + 61) * hop + fft
                if end > sample_count:
                    break
                pooled = scores[0, first:first + 62].max(axis=0)
                maximum = np.maximum(maximum, pooled)
                for i in np.flatnonzero(pooled >= self.thresholds):
                    events.append(dict(label=classes[i], start_s=(start + first * hop) / sample_rate,
                                       end_s=min(end / sample_rate, duration)))
        respiratory = respiratory_measurements([], duration)
        respiratory['reason'] = 'model_does_not_support_phases'
        return BackendOutput(dict(
            schema_version='lung-analysis-v1', mode='lung', model_version='EXP-L030-frame-temporal-delta',
            quality=dict(valid=True, reason=None), supported_classes=classes,
            analyzed_duration_s=duration, phase_intervals=[], respiratory=respiratory,
            sound_events=sorted(events, key=lambda event: event['start_s']),
            class_scores=[dict(label=label, maximum_frame_score=float(maximum[i]),
                               threshold=float(self.thresholds[i])) for i, label in enumerate(classes)],
            limitations=['Engineering test only. Intervals indicate positive clips and may overlap.',
                         'Scores are uncalibrated. L030 does not estimate respiratory phases or rate.']),
            'partial', [AnalysisError('LUNG_INSUFFICIENT_CYCLES', 'L030 does not estimate respiratory phases.', 'respiratory')])


def l030_definition(pipeline: Path) -> BackendDefinition:
    folder = pipeline / 'results/EXP-L030-frame-temporal-delta'
    return BackendDefinition('lung', 'local-engineering-clip-v1', lambda: L030ClipBackend(folder),
                             'EXP-L030-frame-temporal-delta', True, False, True)


def definitions(manifest, *, exclude=frozenset()):
    config=json.loads(Path(manifest).read_text())
    if config.get('scope')!='engineering_test_only' or config.get('deployment_eligible') is not False:
        raise ValueError('Explicit engineering manifest required')
    result=[]
    for mode,item in config['models'].items():
        if mode in exclude:
            continue
        if mode not in ('heart','abdomen','lung') or not item['hashes']:
            raise ValueError('Unsupported engineering model')
        for key,expected in item['hashes'].items():
            if digest(Path(item[key]))!=expected:
                raise ValueError('Engineering source hash mismatch')
        if mode != 'lung' and (not np.isfinite(item['threshold']) or not 0<=item['threshold']<=1):
            raise ValueError('Invalid threshold')
        result.append(BackendDefinition(mode,'local-engineering-v1',lambda m=mode,i=item:LungTestBackend(i) if m=='lung' else TestBackend(m,i),
                                       item['version'],True,False,True))
    return result
