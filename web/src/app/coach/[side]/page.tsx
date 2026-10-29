import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CoachBoard } from "@/components/CoachBoard";
import { api, apiOrNull } from "@/lib/api";
import type { Card, CardResult, CoachHistory } from "@/lib/api";

type Props = { params: Promise<{ side: string }> };

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Coach" };

const SIDES = [
  { id: "wolf", label: "Wolves", roles: ["Werewolf"] },
  { id: "villager", label: "Villagers", roles: ["Villager", "Seer", "Doctor"] },
] as const;

export default async function CoachPage({ params }: Props) {
  const { side } = await params;
  const history = await apiOrNull<CoachHistory>(`/coach/${side}`);
  if (!history) notFound();
  const [cards, results] = await Promise.all([api<Card[]>("/strategies"), api<CardResult[]>("/results")]);
  const mine = SIDES.find((s) => s.id === side);
  const roles: readonly string[] = mine?.roles ?? [];

  return (
    <CoachBoard
      side={side}
      label={mine?.label ?? side}
      sides={SIDES.map(({ id, label }) => ({ id, label }))}
      cards={cards.filter((c) => roles.includes(c.role))}
      generations={history.generations}
      results={results}
    />
  );
}
