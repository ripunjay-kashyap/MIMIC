import { ReplayView } from "@/components/ReplayView";
export default async function ReplayPage({ params, searchParams }: { params: Promise<{ id: string; pid: string }>; searchParams: Promise<{ step?: string | string[] }> }) {
  const [{ id, pid }, search] = await Promise.all([params, searchParams]);
  return <ReplayView key={`${id}-${pid}`} id={id} personaId={pid} target={Array.isArray(search.step) ? search.step[0] : search.step} />;
}
