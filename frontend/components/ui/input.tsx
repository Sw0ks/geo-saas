"use client";

import { type InputHTMLAttributes, forwardRef } from "react";
import { clsx } from "clsx";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-sm font-medium text-gray-700">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={id}
          className={clsx(
            "w-full rounded-lg border px-3 py-2.5 text-sm text-gray-900",
            "placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500",
            "transition-colors",
            error
              ? "border-red-400 focus:ring-red-400"
              : "border-gray-300 bg-white",
            className,
          )}
          {...props}
        />
        {error && (
          <p className="text-xs text-red-500">{error}</p>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";
