import type { Metadata, Viewport } from "next";
import { Barlow_Condensed, Courier_Prime } from "next/font/google";
import { Tabs } from "@/components/Tabs";
import "./globals.css";
import styles from "./layout.module.css";

const courier = Courier_Prime({
  weight: ["400", "700"],
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-courier",
  display: "swap",
});

const barlow = Barlow_Condensed({
  weight: ["500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-barlow",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Werewolf Coach", template: "%s | Werewolf Coach" },
  description:
    "AI agents play Werewolf from swappable strategy cards. See what each player said, what it privately thought, which strategies win, and what the coach changed.",
};

export const viewport: Viewport = { themeColor: "#0e1013", colorScheme: "dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${courier.variable} ${barlow.variable}`}>
      <body>
        <a href="#main" className="skip">
          Skip to the page
        </a>
        <div className={styles.frame}>
          <Tabs />
          <main id="main" className={styles.main}>
            {children}
          </main>
          <footer className={styles.footer}>
            <p>
              Every player on this site is an AI agent. Games were played under two rule sets, and
              results are always shown per rule set.
            </p>
          </footer>
        </div>
      </body>
    </html>
  );
}
