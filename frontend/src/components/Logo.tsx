export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#a99dff" />
          <stop offset="1" stopColor="#2dd4bf" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="#131826" stroke="#262e40" />
      <path d="M10 42 C22 18, 42 18, 54 42" fill="none" stroke="url(#lg)" strokeWidth="5" strokeLinecap="round" />
      <path d="M10 42 H54" stroke="url(#lg)" strokeWidth="5" strokeLinecap="round" />
      <path d="M22 42 V31 M32 42 V26 M42 42 V31" stroke="url(#lg)" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
