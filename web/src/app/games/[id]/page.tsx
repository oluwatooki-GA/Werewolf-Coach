import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ReplayView } from "@/components/ReplayView";
import { apiOrNull } from "@/lib/api";
import type { Replay } from "@/lib/api";
import { cardParts } from "@/lib/format";
import styles from "./replay.module.css";

type Props = { params: Promise<{ id: string }> };

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `Replay ${id}` };
}

/** "fake seer wolves against track votes villagers", from the cards the seats played. */
function matchup(replay: Replay): string {
  const pick = (role: string) => {
    const seat = replay.players.find((p) => p.role === role && p.card);
    return seat?.card ? cardParts(seat.card).name : null;
  };
  const wolves = pick("Werewolf");
  const village = pick("Villager");
  if (!wolves && !village) return "Default strategies on both sides.";
  return `${wolves ?? "default"} wolves against ${village ?? "default"} villagers.`;
}

export default async function ReplayPage({ params }: Props) {
  const { id } = await params;
  const replay = await apiOrNull<Replay>(`/games/${id}/replay`);
  if (!replay) notFound();
  return (
    <>
      <div className={`on-house ${styles.heading}`}>
        <h1>Seed {replay.seed}</h1>
        <p>
          {matchup(replay)} Played by {replay.model || "scripted agents"} on the {replay.rule_version}{" "}
          rules.
        </p>
      </div>
      <ReplayView replay={replay} />
    </>
  );
}
