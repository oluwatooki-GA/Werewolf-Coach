import type { Metadata } from "next";
import { PlayBoard } from "@/components/PlayBoard";
import { api } from "@/lib/api";
import type { Card, PlayStatus, PlayTable } from "@/lib/api";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Play" };

export default async function PlayPage() {
  const [cards, status, table] = await Promise.all([
    api<Card[]>("/strategies"),
    api<PlayStatus>("/play/status"),
    api<PlayTable>("/play/table"),
  ]);
  return <PlayBoard cards={cards} status={status} table={table} />;
}
