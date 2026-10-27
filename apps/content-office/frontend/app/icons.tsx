const paths: Record<string, React.ReactNode> = {
  news: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 8h8M8 12h3M8 16h8M15 12h1" />
    </>
  ),
  pen: (
    <>
      <path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14v6Z" />
      <path d="m5 14 5 5" />
    </>
  ),
  package: (
    <>
      <path d="m3 7 9-5 9 5v10l-9 5-9-5V7ZM3 7l9 5 9-5M12 12v10M7 4.7 17 10" />
    </>
  ),
  activity: (
    <>
      <path d="M3 12h4l3-8 4 16 3-8h4" />
    </>
  ),
  map: (
    <>
      <path d="m3 6 6-2 6 2 6-2v14l-6 2-6-2-6 2V6ZM9 4v14M15 6v14" />
    </>
  ),
  arrow: (
    <>
      <path d="M4 12h16m-6-6 6 6-6 6" />
    </>
  ),
  external: (
    <>
      <path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7a9 9 0 1 0 1 9M20 3v5h-5" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
    </>
  ),
  play: <path d="m9 5 11 7-11 7V5Z" />,
  file: (
    <>
      <path d="M14 2H5v20h14V7l-5-5ZM14 2v6h6M8 13h8M8 17h6" />
    </>
  ),
  source: (
    <>
      <path d="M9 15 15 9m-7 8H6a4 4 0 0 1-3-7l4-4a4 4 0 0 1 6 0m-2 12a4 4 0 0 0 6 0l4-4a4 4 0 0 0-3-7h-2" />
    </>
  ),
  alert: (
    <>
      <path d="m12 3 10 18H2L12 3ZM12 9v5M12 17h.01" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
};

export function Icon({
  name,
  size = 20,
  className = "",
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {paths[name] ?? paths.file}
    </svg>
  );
}
