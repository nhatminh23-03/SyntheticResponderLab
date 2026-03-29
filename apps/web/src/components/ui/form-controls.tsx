import { ChangeEvent, type FormEvent, ReactNode } from "react";

import { cn } from "@/lib/utils";

type FieldProps = {
  label: string;
  hint?: string;
  error?: string | null;
  className?: string;
  children: ReactNode;
};

export function Field({ label, hint, error, className, children }: FieldProps) {
  return (
    <label className={cn("block", className)}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-app-text">{label}</span>
      </div>
      {children}
      {hint ? <p className="mt-2 text-xs leading-5 text-app-muted">{hint}</p> : null}
      {error ? <p className="mt-2 text-xs leading-5 text-app-gold">{error}</p> : null}
    </label>
  );
}

type BaseInputProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
};

export function TextInput({
  value,
  onChange,
  placeholder,
  inputMode,
}: BaseInputProps) {
  return (
    <input
      type="text"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      inputMode={inputMode}
      className="w-full rounded-2xl border border-white/8 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 focus:border-app-cyan/35 focus:bg-[rgba(255,255,255,0.05)] focus:shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
    />
  );
}

type SelectInputProps = {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
};

export function SelectInput({
  value,
  onChange,
  options,
}: SelectInputProps) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full appearance-none rounded-2xl border border-white/8 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm text-app-text outline-none transition focus:border-app-cyan/35 focus:bg-[rgba(255,255,255,0.05)] focus:shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

type ToggleChipProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
};

export function ToggleChip({ checked, onChange, label }: ToggleChipProps) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm transition",
        checked
          ? "border-app-cyan/30 bg-[rgba(15,216,255,0.14)] text-app-cyan"
          : "border-white/8 bg-white/[0.03] text-app-muted hover:border-white/14 hover:text-app-text"
      )}
      aria-pressed={checked}
    >
      <span
        className={cn(
          "inline-flex h-2.5 w-2.5 rounded-full",
          checked ? "bg-app-cyan" : "bg-white/20"
        )}
      />
      {label}
    </button>
  );
}

type TextAreaInputProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
};

export function TextAreaInput({
  value,
  onChange,
  placeholder,
  rows = 5,
}: TextAreaInputProps) {
  return (
    <textarea
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full resize-none rounded-[1.45rem] border border-white/8 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 focus:border-app-cyan/35 focus:bg-[rgba(255,255,255,0.05)] focus:shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
    />
  );
}

type TagMultiSelectProps = {
  options: string[];
  value: string[];
  onChange: (value: string[]) => void;
};

export function TagMultiSelect({
  options,
  value,
  onChange,
}: TagMultiSelectProps) {
  function handleToggle(option: string) {
    if (value.includes(option)) {
      onChange(value.filter((item) => item !== option));
      return;
    }
    onChange([...value, option]);
  }

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value.includes(option);

        return (
          <button
            key={option}
            type="button"
            onClick={() => handleToggle(option)}
            className={cn(
              "rounded-full border px-3 py-2 text-sm transition",
              selected
                ? "border-app-cyan/35 bg-[rgba(15,216,255,0.14)] text-app-cyan"
                : "border-white/8 bg-white/[0.03] text-app-muted hover:border-white/14 hover:text-app-text"
            )}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}

export function normalizeTextInputValue(event: ChangeEvent<HTMLInputElement>) {
  return event.target.value;
}

type TokenInputProps = {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  addLabel?: string;
};

export function TokenInput({
  value,
  onChange,
  placeholder = "Type and press Enter",
  addLabel = "Add",
}: TokenInputProps) {
  function addToken(rawValue: string) {
    const nextToken = rawValue.trim();
    if (!nextToken) {
      return;
    }
    if (value.includes(nextToken)) {
      return;
    }
    onChange([...value, nextToken]);
  }

  return (
    <div className="rounded-[1.45rem] border border-white/8 bg-[rgba(255,255,255,0.03)] p-3">
      <TokenComposer
        onAdd={addToken}
        placeholder={placeholder}
        addLabel={addLabel}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        {value.length === 0 ? (
          <span className="text-xs text-app-muted">
            No items added yet.
          </span>
        ) : null}
        {value.map((token) => (
          <button
            key={token}
            type="button"
            onClick={() => onChange(value.filter((item) => item !== token))}
            className="inline-flex items-center gap-2 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-sm text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
          >
            <span>{token}</span>
            <span className="text-app-muted">×</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function TokenComposer({
  onAdd,
  placeholder,
  addLabel,
}: {
  onAdd: (value: string) => void;
  placeholder: string;
  addLabel: string;
}) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const rawValue = String(formData.get("token") ?? "");
    onAdd(rawValue);
    form.reset();
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        name="token"
        type="text"
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-2xl border border-white/8 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 focus:border-app-cyan/35 focus:bg-[rgba(255,255,255,0.05)] focus:shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
      />
      <button
        type="submit"
        className="rounded-2xl border border-app-border bg-white/[0.03] px-4 py-3 text-sm font-medium text-app-text transition hover:border-app-cyan/30 hover:text-app-cyan"
      >
        {addLabel}
      </button>
    </form>
  );
}
