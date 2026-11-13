# H021 TRAIN-only result

{
  "metrics": {
    "experiment": "EXP-H021-fold-local-hard-negative-acoustic-mining",
    "population": "568 TRAIN outer-fold OOF participants",
    "threshold": 0.19225345646277395,
    "accuracy": 0.7746478873239436,
    "precision": 0.4583333333333333,
    "sensitivity": 0.9,
    "specificity": 0.7445414847161572,
    "f1": 0.6073619631901841,
    "balanced_accuracy": 0.8222707423580786,
    "tn": 341,
    "fp": 117,
    "fn": 11,
    "tp": 99,
    "roc_auc": 0.9028185788011115,
    "pr_auc": 0.8302493862488574,
    "confusion_matrix": [
      [
        341,
        117
      ],
      [
        11,
        99
      ]
    ],
    "external_validation_opened": false,
    "sealed_test_opened": false,
    "protocol_sha256": "fc288f92085ab8c0487a98bf6b36298e4c061fe9edc6049f33229fe0a5ee533c",
    "eligible_for_external_validation": false,
    "minimum_meaningful": true,
    "strong": true,
    "very_strong": true,
    "breakthrough": false
  },
  "h020_to_h021_delta": {
    "fp": -62,
    "fn": 0,
    "sensitivity": 0.0,
    "specificity": 0.1353711790393013,
    "precision": 0.10221822541966424,
    "f1": 0.09705268483966867,
    "roc_auc": 0.010381103612544518,
    "pr_auc": 0.016422800998718956
  },
  "decision": "strong",
  "external_validation_opened": false,
  "sealed_test_opened": false,
  "next": "Stop; no H022 automatically"
}
