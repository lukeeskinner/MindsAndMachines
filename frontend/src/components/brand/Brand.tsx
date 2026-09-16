import { Waypoints } from "lucide-react";

export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <span className={`brand-mark-shared ${className}`} aria-hidden="true">
      <Waypoints size={25} strokeWidth={1.8} />
    </span>
  );
}

export function BrandWordmark({
  className = "",
  label = "Minds and Machines",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <span className={`brand-wordmark ${className}`} aria-label={label}>
      <BrandMark />
      <span>
        minds &<br />
        machines<span className="text-teal-dark">.</span>
      </span>
    </span>
  );
}
