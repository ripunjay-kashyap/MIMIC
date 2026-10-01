import type { Metadata } from "next";
import { ReportView } from "@/components/ReportView";

export const metadata: Metadata = {
  title: "Run report",
  description: "MIMIC run report: completion, abandonment, routes and backtracks across six AI personas, with findings split into Observed, Evidence, Interpretation and Suggested investigation.",
};

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportView key={id} id={id} />;
}
