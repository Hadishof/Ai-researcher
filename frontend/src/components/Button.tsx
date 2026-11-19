// The one button used everywhere, so every button has the same states:
// hover, keyboard focus outline, disabled, and loading (spinner + disabled).

import { LoaderCircle } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

// ComponentProps<"button">: every normal <button> prop (onClick, aria-label, ref...).
interface ButtonProps extends ComponentProps<"button"> {
  variant?: Variant; // primary = solid accent, secondary = outline, danger = red, ghost = icon/quiet
  size?: "md" | "sm";
  loading?: boolean;
  icon?: ReactNode; // a small lucide icon shown before the label
}

export default function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  disabled,
  className = "",
  children,
  type = "button", // not "submit" by default, so a button never submits a form by accident
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`btn btn-${variant} btn-${size} ${children ? "" : "btn-icon"} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <LoaderCircle className="spin" size={16} aria-hidden /> : icon}
      {children}
    </button>
  );
}
