import type { Metadata } from "next";
import { CaseStudy } from "@/components/CaseStudy";

export const metadata: Metadata = {
  title: "Case study",
  description: "One recorded MIMIC run told as a story: six AI personas try to buy a health-insurance policy on a seeded demo site. Three gave up on the same mobile OTP page; 6 of 12 seeded defects found, 11 evidence-backed findings.",
};

export default function CaseStudyPage() {
  return <CaseStudy />;
}
