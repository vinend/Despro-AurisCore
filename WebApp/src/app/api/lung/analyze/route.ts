import { createAnalysisHandler } from "@/lib/auriscore/analysis-route.server";
export const runtime = "nodejs";
export const POST = createAnalysisHandler("lung");
