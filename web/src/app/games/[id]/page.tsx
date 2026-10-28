import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ChatAvatar } from "@/components/ChatAvatar";
import { Room } from "@/components/Room";
import { apiOrNull } from "@/lib/api";
import type { Replay } from "@/lib/api";
import { cardParts, plural } from "@/lib/format";

type Props = { params: Promise<{ id: string }> };

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `Replay ${id}` };
}

/** "Fake seer wolves against track votes villagers", from the cards the seats played. */
function matchup(replay: Replay): string {
  const pick = (role: string) => {
    const seat = replay.players.find((p) => p.role === role && p.card);
    return seat?.card ? cardParts(seat.card).name : null;
  };
  const wolves = pick("Werewolf");
  const village = pick("Villager");
  const text =
    !wolves && !village
      ? "Default strategies on both sides"
      : `${wolves ?? "default"} wolves against ${village ?? "default"} villagers`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default async function ReplayPage({ params }: Props) {
  const { id } = await params;
  const replay = await apiOrNull<Replay>(`/games/${id}/replay`);
  if (!replay) notFound();
  return (
    <Room
      entries={replay.entries}
      players={replay.players}
      title={`Game ${replay.id}`}
      avatar={<ChatAvatar kind={replay.winner} size={40} />}
      label={`Seed ${replay.seed}`}
      welcome={
        <>
          <p>
            This game is over, so the roles and every private thought are shown. Tap a message to read what its
            player was thinking.
          </p>
          <p>
            {matchup(replay)}, played by {replay.model || "scripted agents"} on the {replay.rule_version} rules,{" "}
            {plural(replay.rounds, "round")}.
          </p>
        </>
      }
    />
  );
}
