export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
export const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";
export const DEMO_GOAL = "Choose a health insurance plan, complete onboarding, and reach the policy confirmation page.";
