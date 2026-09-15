import { PRESETS } from "../presets.js";
import Button from "./Button.jsx";

export default function PresetPicker({ onPick }) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(PRESETS).map(([key, preset]) => (
        <Button key={key} variant="secondary" onClick={() => onPick(preset.payload)}>
          {preset.label}
        </Button>
      ))}
    </div>
  );
}
