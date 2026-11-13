import { createLiveAnalysisHandler } from "@/lib/auriscore/live-analysis-route.server";
export const runtime = "nodejs";
export const POST = createLiveAnalysisHandler();
