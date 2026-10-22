import type { Metadata } from "next";
import Link from "next/link";
import { TeamMark } from "@/components/TeamMark";
import { api } from "@/lib/api";
import type { GameList, GameSummary } from "@/lib/api";
import { cardParts, gel, plural, ruleLabel } from "@/lib/format";
import styles from "./games.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Replays" };

const PAGE = 25;

type Search = { winner?: string; rules?: string; players?: string; page?: string };

function cardsOf(game: GameSummary): { wolves: string | null; village: string | null } {
  const refs = [...new Set(Object.values(game.cards))];
  const name = (prefix: string) => {
    const ref = refs.find((r) => r.startsWith(prefix));
    return ref ? cardParts(ref).name : null;
  };
  return { wolves: name("wolf."), village: name("villager.") };
}

/** A link to this list with some filters changed. Changing a filter goes back to page one. */
function href(search: Search, change: Partial<Search>): string {
  const merged: Search = { ...search, page: undefined, ...change };
  const query = new URLSearchParams(
    Object.entries(merged).filter(([, v]) => v) as [string, string][],
  ).toString();
  return query ? `/games?${query}` : "/games";
}

function Choice({
  search,
  field,
  value,
  children,
}: {
  search: Search;
  field: "winner" | "rules" | "players";
  value: string;
  children: React.ReactNode;
}) {
  const current = (search[field] ?? (field === "players" ? "ai" : "")) === value;
  return (
    <Link href={href(search, { [field]: value })} aria-current={current ? "true" : undefined}>
      {children}
    </Link>
  );
}

export default async function GamesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const page = Math.max(1, Number(search.page) || 1);
  const query = new URLSearchParams({ limit: String(PAGE), offset: String((page - 1) * PAGE) });
  if (search.winner === "Wolves" || search.winner === "Village") query.set("winner", search.winner);
  if (search.rules === "v1" || search.rules === "v2") query.set("rule_version", search.rules);
  // scripted games are test fixtures with no model, so the list opens on the AI players
  const players = search.players === "scripted" ? "scripted" : search.players === "any" ? null : "ai";
  if (players) query.set("players", players);
  const { total, games } = await api<GameList>(`/games?${query}`);
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <section className={styles.sheet} aria-labelledby="games">
      <header className={styles.head}>
        <h1 id="games">Replays</h1>
        <p>
          {plural(total, "game")}
          {players === "ai"
            ? " played by AI agents. Scripted test games are one filter away."
            : players === "scripted"
              ? " played by scripted test agents."
              : " in all."}{" "}
          Open one to read it as a script, with each player&apos;s private notes on the facing page.
        </p>
        <nav className={styles.filters} aria-label="Filter the games">
          <div className={styles.group}>
            <span>Winner</span>
          <Choice search={search} field="winner" value="">
            Any
          </Choice>
          <Choice search={search} field="winner" value="Wolves">
            Wolves
          </Choice>
          <Choice search={search} field="winner" value="Village">
            Village
          </Choice>
          </div>
          <div className={styles.group}>
            <span>Players</span>
          <Choice search={search} field="players" value="ai">
            AI agents
          </Choice>
          <Choice search={search} field="players" value="scripted">
            Scripted tests
          </Choice>
          <Choice search={search} field="players" value="any">
            Any
          </Choice>
          </div>
          <div className={styles.group}>
            <span>Rules</span>
          <Choice search={search} field="rules" value="">
            Any
          </Choice>
          <Choice search={search} field="rules" value="v1">
            v1
          </Choice>
          <Choice search={search} field="rules" value="v2">
            v2
          </Choice>
          </div>
        </nav>
      </header>

      {games.length === 0 ? (
        <p className={styles.empty}>No games match. Clear a filter to see them all.</p>
      ) : (
        <table className={styles.table}>
          <caption className="visually-hidden">Saved games</caption>
          <thead>
            <tr>
              <th scope="col">Game</th>
              <th scope="col">Winner</th>
              <th scope="col">Rounds</th>
              <th scope="col">Strategies</th>
              <th scope="col">Played by</th>
              <th scope="col">Rules</th>
            </tr>
          </thead>
          <tbody>
            {games.map((game) => {
              const cards = cardsOf(game);
              return (
                <tr key={game.id} style={{ ["--gel" as string]: gel(game.id) }}>
                  <th scope="row">
                    <Link href={`/games/${game.id}`}>Seed {game.seed}</Link>
                    <small>{game.id}</small>
                  </th>
                  <td data-label="Winner">
                    <TeamMark team={game.winner} word />
                  </td>
                  <td data-label="Rounds">{game.rounds}</td>
                  <td data-label="Strategies">
                    {cards.wolves || cards.village ? (
                      <>
                        {cards.wolves ?? "default"} wolves, {cards.village ?? "default"} villagers
                      </>
                    ) : (
                      <span className={styles.dim}>defaults</span>
                    )}
                  </td>
                  <td data-label="Played by">{game.model || "scripted"}</td>
                  <td data-label="Rules" title={ruleLabel(game.rule_version)}>
                    {game.rule_version}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {pages > 1 ? (
        <nav className={styles.pager} aria-label="Pages">
          {page > 1 ? (
            <Link href={href(search, { page: String(page - 1) })}>Earlier</Link>
          ) : (
            <span />
          )}
          <span>
            Page {page} of {pages}
          </span>
          {page < pages ? (
            <Link href={href(search, { page: String(page + 1) })}>Later</Link>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </section>
  );
}
