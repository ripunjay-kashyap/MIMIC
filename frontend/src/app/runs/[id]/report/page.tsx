import { ReportView } from "@/components/ReportView";
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportView key={id} id={id} />;
}
