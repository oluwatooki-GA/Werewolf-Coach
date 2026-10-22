import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";
import styles from "./layout.module.css";

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
    "AI agents play Werewolf from swappable strategy cards. Read their games as a chatroom, see what each player privately thought, which strategies win, and what the coach changed.",
};

export const viewport: Viewport = { themeColor: "#2b2d31", colorScheme: "dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={figtree.variable}>
      <body>
        <a href="#main" className="skip">
          Skip to the page
        </a>
        <div className={styles.shell}>
          <Sidebar />
          <main id="main" className={styles.main}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
