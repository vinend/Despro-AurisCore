"""Read-only preflight by default; explicit, capped GPU execution on the destination."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import shutil
import sys
import tempfile
from importlib.metadata import version

HERE=Path(__file__).resolve().parent
PIPE=HERE.parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(PIPE/'src'))
ID='RD-H022-TMIL-P1'
MANIFEST='fedc1166f6cdbbd44b82aab5a054dbca4c536bb9298a463315a180112b6ab83e'
SOURCE_MACHINE='2218d361f7de2fdf62801fcf6b3fd176c95d2a31cb3fc39d3e7d144ae66d58f9'


def sha(file):
    with file.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def verify_private(root):
    path=root/'manifest.json'
    if sha(path)!=MANIFEST:
        raise ValueError('Wrong TRAIN transfer manifest')
    expected=json.loads(path.read_text())
    for rel,digest in expected.items():
        path=root/rel
        if not path.resolve().is_relative_to(root) or sha(path)!=digest:
            raise ValueError(f'Private artifact changed: {rel}')
    # Reject previously absent TSVs and any unexpected data inserted into this bundle.
    files={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if files!=set(expected)|{'manifest.json'}:
        raise ValueError('Unexpected file in sealed input tree')
    return len(expected)


def destination_guard():
    if sha(Path('/etc/machine-id'))==SOURCE_MACHINE:
        raise RuntimeError('Training is disabled on the preparation laptop')


def environment():
    if sys.platform!='linux' or sys.version_info[:2]!=(3,13):
        raise RuntimeError('Use Linux/WSL2 and Python 3.13 with the supplied lock')
    for name,wanted in [('tensorflow','2.20.0'),('keras','3.15.1'),('numpy','2.2.6'),
                        ('scipy','1.15.3'),('scikit-learn','1.6.1'),('librosa','0.11.0')]:
        if version(name)!=wanted:
            raise ValueError(f'Environment mismatch for {name}')
    if os.environ.get('HEART_LIBS_READY')!='1':
        libs=sorted((Path(sys.prefix)/'lib/python3.13/site-packages/nvidia').glob('*/lib'))
        env=dict(os.environ,HEART_LIBS_READY='1',TF_DETERMINISTIC_OPS='1',TF_CUDNN_USE_AUTOTUNE='0',
                 LD_LIBRARY_PATH=':'.join([*(str(p) for p in libs),os.environ.get('LD_LIBRARY_PATH','')]))
        os.execve(sys.executable,[sys.executable,*sys.argv],env)


def gpu():
    import tensorflow as tf
    devices=tf.config.list_physical_devices('GPU')
    if not devices:
        raise RuntimeError('No TensorFlow CUDA GPU. CPU training disabled.')
    for device in devices:
        tf.config.experimental.set_memory_growth(device,True)
    with tf.device('/GPU:0'):
        result=tf.matmul(tf.ones([2,2]),tf.ones([2,2]))
    if 'GPU:0' not in result.device or float(result[0,0])!=2:
        raise RuntimeError('GPU operation failed')
    return tf.config.experimental.get_device_details(devices[0]).get('device_name','GPU:0')


def preflight(root, output_parent):
    import numpy as np
    import tensorflow as tf
    from experiment import fold_data, embeddings, record, build_model, bind, LogMelCache
    from auriscore.temporal_mil_engine import predict_recording
    checked=verify_private(root)
    if not output_parent.is_dir() or shutil.disk_usage(output_parent).free < 12*1024**3:
        raise ValueError('Existing writable output parent with >=12 GiB free required')
    device=gpu()
    with tempfile.TemporaryDirectory(dir=output_parent) as temp:
        for fold in range(1,6):
            data=fold_data(root,fold)
            bind(data)
            src=root/'h022'/f'fold-{fold}'
            embeddings(src/'train_embeddings.csv',data,['fit','early_stop'])
            model=build_model(str(src/'acoustic.keras'),42+fold)
            # Compare the actual H022 feature map to the transferred, pre-pooling trunk.
            original=tf.keras.models.load_model(src/'acoustic.keras',compile=False)
            cache=LogMelCache(root,Path(temp),fold,src/'normalization.json')
            rid=data.ids('early_stop',True)[0]
            r=record(data,cache,rid,'early_stop')
            x=r['x'][:1]
            trunk=next(layer for layer in model.layers if isinstance(layer,tf.keras.Model))
            np.testing.assert_array_equal(tf.keras.Model(original.input,original.layers[12].output)(x,training=False),
                                          trunk(x,training=False))
            result=predict_recording(model,r)
            if not np.isfinite(result['probability']) or not np.any(result['murmur']['valid']):
                raise ValueError('Invalid temporal smoke inference')
            print(f'Fold {fold}: roles, coefficients, H022 transfer, temporal inference PASS',flush=True)
            tf.keras.backend.clear_session()
    print(json.dumps(dict(preflight='PASS',training_started=False,device=device,private_files=checked)),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','train','_worker','verify-results'])
    parser.add_argument('--inputs',required=True,type=Path)
    parser.add_argument('--runs',required=True,type=Path)
    args=parser.parse_args()
    environment()
    root=args.inputs.resolve()
    runs=args.runs.resolve()
    if runs.is_relative_to(root) or runs.is_relative_to(PIPE.parent) or runs==root:
        raise ValueError('Keep runs outside the input bundle and Git working tree')
    output=runs/ID
    watchdog=runs/(ID+'-watchdog')
    claim=runs/(ID+'.claim')
    if args.action=='check':
        preflight(root,runs)
        return 0
    if args.action=='verify-results':
        from review import verify_result
        verify_private(root)
        gpu()
        verify_result(root,output)
        return 0
    destination_guard()
    if args.action=='_worker':
        if not claim.is_file() or claim.read_text()!=os.environ.get('HEART_RUN_TOKEN'):
            raise ValueError('Missing supervisor claim')
        from experiment import run
        gpu()
        run(root,output)
        return 0
    if any(p.exists() for p in (claim,watchdog,output)):
        raise FileExistsError('Existing run or claim. No retries.')
    subprocess.run([sys.executable,__file__,'check','--inputs',str(root),'--runs',str(runs)],check=True)
    from auriscore.temporal_mil_runtime import supervise
    token=secrets.token_hex(32)
    with claim.open('x') as f:
        f.write(token)
    os.environ['HEART_RUN_TOKEN']=token
    print(f'Worker progress: {watchdog}/worker.log',flush=True)
    return supervise([sys.executable,str(Path(__file__).resolve()),'_worker','--inputs',str(root),'--runs',str(runs)],watchdog,43200)


if __name__=='__main__':
    sys.exit(main())
