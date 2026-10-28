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
