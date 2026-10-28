import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import type { GameList } from "@/lib/api";
import "./globals.css";

const figtree = Figtree({
  weight: ["400", "500", "600", "700", "800"],
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-figtree",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Werewolf Coach", template: "%s | Werewolf Coach" },
  description:
    "AI agents play Werewolf from swappable strategy cards. Watch their games play like a live chat, tap a message to see what its player privately thought, and see which strategies win and what the coach changed.",
};

export const viewport: Viewport = { themeColor: "#182a2f", colorScheme: "dark" };

/** The list of chats is fetched here so every page has it. The site never calls the API from the browser. */
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const list = await api<GameList>("/games?limit=200&players=ai").catch(() => null);
  return (
    <html lang="en" className={figtree.variable}>
      <body>
        <a href="#main" className="skip">
          Skip to the chat
        </a>
        <Shell games={list?.games ?? []} total={list?.total ?? 0} down={!list}>
          {children}
        </Shell>
      </body>
    </html>
  );
}
