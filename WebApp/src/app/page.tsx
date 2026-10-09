import { MainScreen } from "@/components/auriscore/main-screen";
import { TrainingMetricsCard } from "@/components/auriscore/training-metrics-card";
import { loadTrainingMetrics } from "@/lib/auriscore/training-metrics.server";

export default async function Home() {
  const trainingMetrics = await loadTrainingMetrics();

  return (
    <MainScreen
      trainingMetricsCard={<TrainingMetricsCard metrics={trainingMetrics} />}
    />
  );
}
