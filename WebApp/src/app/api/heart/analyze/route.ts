import { createAnalysisHandler } from "@/lib/auriscore/analysis-route.server";
export const runtime = "nodejs";
/** Preserve the existing client contract while sharing the retained worker. */
export const POST = createAnalysisHandler("heart", true);
