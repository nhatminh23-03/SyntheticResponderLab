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
      {error ? <p className="mt-2 text-xs leading-5 text-app-warning">{error}</p> : null}
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
      className="w-full rounded-2xl border px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 [background:var(--control-bg)] [border-color:var(--control-border)] focus:[border-color:var(--color-border-strong)] focus:[background:var(--control-bg-hover)] focus:[box-shadow:var(--focus-ring-shadow)]"
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
    <div className="relative">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="theme-select w-full appearance-none rounded-2xl border px-4 py-3 pr-11 text-sm text-app-text outline-none transition [background:var(--control-bg)] [border-color:var(--control-border)] focus:[border-color:var(--color-border-strong)] focus:[background:var(--control-bg-hover)] focus:[box-shadow:var(--focus-ring-shadow)]"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-app-muted"
      >
        <ChevronDownIcon />
      </span>
    </div>
  );
}

function ChevronDownIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="m5 7.5 5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
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
          ? "text-app-cyan [border-color:var(--color-border-strong)] [background:var(--color-brand-primary-soft)]"
          : "text-app-muted [background:var(--control-bg)] [border-color:var(--control-border)] hover:text-app-text [box-shadow:inset_0_0_0_1px_var(--control-border)]"
      )}
      aria-pressed={checked}
    >
      <span
        className={cn(
          "inline-flex h-2.5 w-2.5 rounded-full",
          checked ? "bg-app-cyan" : "[background:var(--badge-neutral-border)]"
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
      className="w-full resize-none rounded-[1.45rem] border px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 [background:var(--control-bg)] [border-color:var(--control-border)] focus:[border-color:var(--color-border-strong)] focus:[background:var(--control-bg-hover)] focus:[box-shadow:var(--focus-ring-shadow)]"
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
                ? "text-app-cyan [border-color:var(--color-border-strong)] [background:var(--color-brand-primary-soft)]"
                : "text-app-muted [background:var(--control-bg)] [border-color:var(--control-border)] hover:text-app-text [box-shadow:inset_0_0_0_1px_var(--control-border)]"
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
  suggestions?: string[];
};

export function TokenInput({
  value,
  onChange,
  placeholder = "Type and press Enter",
  addLabel = "Add",
  suggestions = [],
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
    <div className="rounded-[1.45rem] border p-3 [background:var(--control-bg)] [border-color:var(--control-border)]">
      <TokenComposer
        onAdd={addToken}
        placeholder={placeholder}
        addLabel={addLabel}
      />
      {suggestions.length > 0 ? (
        <div className="mt-3">
          <div className="mb-2 text-xs uppercase tracking-[0.18em] text-app-muted">
            Suggestions — click to add
          </div>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion) => {
              const isAdded = value.includes(suggestion);
              return (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => addToken(suggestion)}
                  disabled={isAdded}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition",
                    isAdded
                      ? "cursor-default text-app-muted/60 [border-color:var(--control-border)] [background:var(--status-neutral-bg)]"
                      : "text-app-muted [border-color:var(--control-border)] hover:border-app-cyan/30 hover:text-app-cyan [background:var(--button-secondary-bg)]"
                  )}
                >
                  {isAdded ? "Added · " : "+ "}
                  {suggestion}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        {value.length === 0 ? (
          <span className="text-xs text-app-muted">
            No items added yet.
          </span>
        ) : null}
        {value.map((token) => (
          <div
            key={token}
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm text-app-text transition [background:var(--control-bg-hover)] [border-color:var(--control-border)] hover:border-app-cyan/25 hover:text-app-cyan"
          >
            <span>{token}</span>
            <button
              type="button"
              aria-label={`Remove ${token}`}
              onClick={() => onChange(value.filter((item) => item !== token))}
              className="text-app-muted transition hover:text-app-cyan"
            >
              ×
            </button>
          </div>
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
        className="min-w-0 flex-1 rounded-2xl border px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted/50 [background:var(--control-bg)] [border-color:var(--control-border)] focus:[border-color:var(--color-border-strong)] focus:[background:var(--control-bg-hover)] focus:[box-shadow:var(--focus-ring-shadow)]"
      />
      <button
        type="submit"
        className="rounded-2xl border px-4 py-3 text-sm font-medium text-app-text transition [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)] hover:border-app-cyan/30 hover:text-app-cyan hover:[background:var(--button-secondary-bg-hover)]"
      >
        {addLabel}
      </button>
    </form>
  );
}
