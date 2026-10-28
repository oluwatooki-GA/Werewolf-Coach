import { Welcome } from "@/components/Welcome";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export default function Home() {
  return <Welcome />;
}
