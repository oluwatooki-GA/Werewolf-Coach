import type { Metadata } from "next";
import { Welcome } from "@/components/Welcome";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Welcome" };

/** The same chat as the home page, at its own address so a phone can open it from the list. */
export default function WelcomePage() {
  return <Welcome />;
}
