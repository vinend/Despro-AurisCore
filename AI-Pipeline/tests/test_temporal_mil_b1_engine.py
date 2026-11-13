"""Actual engine gradient and Adam equivalence, including frozen BatchNorm."""
import unittest
import numpy as np
import tensorflow as tf
from auriscore.temporal_mil_b1 import gradients,executor,verify_contract,CONTRACT_SHA
from auriscore.temporal_mil_engine import batch_step
from auriscore.logmel_temporal_mil import mil_probability

class Tests(unittest.TestCase):
    def test_gradient_adam_and_validation(self):
        tf.keras.utils.set_random_seed(43)
        x=tf.keras.Input((40,313,1));z=tf.keras.layers.AveragePooling2D((40,8))(x)
        z=tf.keras.layers.Reshape((39,1))(z)
        z=tf.keras.layers.BatchNormalization(trainable=False)(z)
        model=tf.keras.Model(x,dict(murmur_logits=tf.keras.layers.Dense(1)(z),phase_logits=tf.keras.layers.Dense(4)(z)))
        records=[]
        for n,y in ((1,1.),(33,0.)):
            records.append(dict(x=np.full((n,40,313,1),.2+y,np.float32),label=y,
                presence_valid=np.ones((n,39),bool),phase=np.zeros((n,39),np.int32),phase_valid=np.ones((n,39),bool)))
        weights=np.array([.6,2.3],np.float32)
        result,actual=gradients(model,records,weights)
        with tf.GradientTape() as tape:
            loss=0.;phase=0.;k=sum(r['phase_valid'].sum() for r in records)
            for r,w in zip(records,weights):
                out=model(r['x'],training=True)
                p=tf.clip_by_value(tf.reduce_mean(mil_probability(out['murmur_logits'],r['presence_valid'])),1e-7,1-1e-7)
                loss+=w*(-r['label']*tf.math.log(p)-(1-r['label'])*tf.math.log(1-p))/2
                phase+=tf.reduce_sum(tf.nn.sparse_softmax_cross_entropy_with_logits(labels=r['phase'],logits=out['phase_logits']))/k
            loss+=.2*phase
        reference=tape.gradient(loss,model.trainable_variables)
        for a,b in zip(actual,reference):np.testing.assert_allclose(a,b,atol=1e-6,rtol=1e-5)
        self.assertAlmostEqual(result['loss'],float(loss),places=6)
        original=[v.numpy().copy() for v in model.weights]
        opt=tf.keras.optimizers.Adam(.0001,clipnorm=1.)
        opt.apply_gradients(zip(reference,model.trainable_variables));expected=[v.numpy().copy() for v in model.weights]
        model.set_weights(original)
        opt2=tf.keras.optimizers.Adam(.0001,clipnorm=1.)
        batch_step(model,records,weights,opt2)
        for a,b in zip(expected,model.weights):np.testing.assert_allclose(a,b,atol=1e-6,rtol=1e-5)
        self.assertEqual(int(opt2.iterations),1)
        before=[v.numpy().copy() for v in model.weights]
        batch_step(model,records,weights)
        for a,b in zip(before,model.weights):np.testing.assert_array_equal(a,b)
        for v,a in zip(model.weights,original):
            if 'moving_' in v.name:np.testing.assert_array_equal(v,a)
        self.assertEqual(executor(model,True).experimental_get_tracing_count(),1)

    def test_contract_hash(self):
        verify_contract(CONTRACT_SHA)
        for value in (None,'','synthetic-test-only','0'*64):
            with self.assertRaises(ValueError):verify_contract(value)

if __name__=='__main__':unittest.main(verbosity=2)
