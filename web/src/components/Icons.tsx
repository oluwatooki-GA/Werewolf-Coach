/** The few icons the messenger needs, drawn once in one 1.8 stroke so they all weigh the same. */

type Props = { size?: number };

function Svg({ size = 22, children }: Props & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const Back = (p: Props) => (
  <Svg {...p}>
    <path d="M19 12H5m6-6-6 6 6 6" />
  </Svg>
);

export const More = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="5" r="1.2" fill="currentColor" />
    <circle cx="12" cy="12" r="1.2" fill="currentColor" />
    <circle cx="12" cy="19" r="1.2" fill="currentColor" />
  </Svg>
);

export const People = (p: Props) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3 19c0-3.2 2.7-5 6-5s6 1.8 6 5" />
    <path d="M16 5.2a3.2 3.2 0 0 1 0 5.6M18 14.4c1.8.6 3 2.1 3 4.6" />
  </Svg>
);

export const Close = (p: Props) => (
  <Svg {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Svg>
);

export const Lock = (p: Props) => (
  <Svg {...p}>
    <rect x="5" y="11" width="14" height="9" rx="2" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </Svg>
);

/** The welcome chat: a crescent moon. */
export const Moon = (p: Props) => (
  <Svg {...p}>
    <path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5Z" />
  </Svg>
);

/** Strategies: a stack of cards. */
export const Cards = (p: Props) => (
  <Svg {...p}>
    <rect x="4" y="7" width="12" height="13" rx="2" />
    <path d="M8 4h10a2 2 0 0 1 2 2v10" />
  </Svg>
);

/** The coach: a whistle. */
export const Coach = (p: Props) => (
  <Svg {...p}>
    <circle cx="9" cy="15" r="5" />
    <path d="M13 11l7-4M9 15v.01M14 7.5h6" />
  </Svg>
);

/** Play: a seat at the table. */
export const Seat = (p: Props) => (
  <Svg {...p}>
    <path d="M6 20v-7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v7M6 20h12M9 11V5h6v6" />
  </Svg>
);

/** Morning: a sun. */
export const Sun = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
  </Svg>
);

/** The vote's result: a ballot box. */
export const Ballot = (p: Props) => (
  <Svg {...p}>
    <path d="M4 14h16v6H4zM8 14V4h8v10" />
    <path d="m10 9 1.5 1.5L14 7.5" />
  </Svg>
);

/** The GitHub mark (from GitHub's Octicons). Filled, unlike the line icons around it. */
export const Github = ({ size = 22 }: Props) => (
  <svg viewBox="0 0 16 16" width={size} height={size} fill="currentColor" aria-hidden="true" focusable="false">
    <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
  </svg>
);

/** The end of the game: a flag. */
export const Flag = (p: Props) => (
  <Svg {...p}>
    <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
  </Svg>
);
