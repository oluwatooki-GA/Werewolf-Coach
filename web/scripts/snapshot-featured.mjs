// Saves the hand-picked games, the strategy cards and the welcome moment from a running API into
// src/data/featured, so the site can show them while the API is asleep. The games to keep are the
// ids in src/data/featured-ids.json; the welcome game must be one of them.
//   API_URL=http://localhost:8000 npm run featured
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";

const API = process.env.API_URL ?? "http://localhost:8000";
const data = new URL("../src/data/", import.meta.url);
const ids = JSON.parse(await readFile(new URL("featured-ids.json", data), "utf8"));

async function get(path) {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return response.json();
}

const list = await get("/games?limit=200&players=ai");
const games = ids.map((id) => {
  const game = list.games.find((g) => g.id === id);
  if (!game) throw new Error(`game ${id} is not in the API's list`);
  return game;
});
const welcome = await get("/featured");
if (!ids.includes(welcome.game_id)) throw new Error(`the welcome game ${welcome.game_id} must be one of the featured ids`);
const cards = await get("/strategies");

await rm(new URL("featured/", data), { recursive: true, force: true });
await mkdir(new URL("featured/replays/", data), { recursive: true });
for (const id of ids) {
  await writeFile(new URL(`featured/replays/${id}.json`, data), JSON.stringify(await get(`/games/${id}/replay`)));
}
await writeFile(new URL("featured/games.json", data), JSON.stringify({ games, welcome, cards }, null, 1));
console.log(`saved ${games.length} games, ${cards.length} cards and the welcome moment from ${API}`);
