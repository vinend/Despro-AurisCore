export interface TrainingMetrics {
  status: string;
  sampleRate: number;
  signalBandMaxHz: number;
  trainSubjects: number;
  trainRecordings: number;
  validationSubjects: number;
  validationRecordings: number;
  threshold: number;
  targetSensitivity: number;
  minimumSpecificity: number;
  constraintsMet: boolean;
  accuracy: number;
  precision: number;
  sensitivity: number;
  specificity: number;
  negativePredictiveValue: number;
  macroF1: number;
  confusionMatrix: [[number, number], [number, number]];
  trainingEpochs: number;
  bestValidationLoss: number;
  warning: string;
}
