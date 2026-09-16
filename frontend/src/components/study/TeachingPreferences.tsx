import { useId } from "react";
import { SlidersHorizontal } from "lucide-react";
import type { LearnerPresentationPreferences } from "../../../../contracts/api";
import { Switch } from "../ui/primitives";

const styles: [keyof LearnerPresentationPreferences, string][] = [
  ["plain_language", "Plain language"],
  ["step_by_step", "Step by step"],
  ["concise", "Keep it concise"],
];

export function TeachingPreferences({
  preferences,
  onChange,
  busy,
}: {
  preferences: LearnerPresentationPreferences;
  onChange: (value: LearnerPresentationPreferences) => void;
  busy: boolean;
}) {
  const id = useId();
  return (
    <div
      className="chat-preferences"
      role="group"
      aria-labelledby={`${id}-title`}
    >
      <div className="chat-preferences-title">
        <SlidersHorizontal size={14} aria-hidden="true" />
        <h3 id={`${id}-title`}>Explanation style</h3>
      </div>
      {styles.map(([key, label]) => (
        <div className="chat-preference" key={key}>
          <label htmlFor={`${id}-${key}`}>{label}</label>
          <Switch
            id={`${id}-${key}`}
            checked={preferences[key]}
            disabled={busy}
            onCheckedChange={(checked) =>
              onChange({ ...preferences, [key]: checked })
            }
            aria-describedby={`${id}-note`}
          />
        </div>
      ))}
      <p id={`${id}-note`}>
        Applies to the next response. Kept when you reset.
      </p>
    </div>
  );
}
