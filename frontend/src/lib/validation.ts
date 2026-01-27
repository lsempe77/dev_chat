/**
 * Form Validation Utilities
 *
 * Provides real-time field validation with specific, actionable feedback.
 * All validators return an error message string if invalid, or null if valid.
 */

export type ValidationResult = string | null;
export type Validator = (value: unknown) => ValidationResult;

// ============================================================================
// Core Validators
// ============================================================================

/**
 * Checks if a value is required (non-empty)
 */
export const required = (message = "This field is required"): Validator =>
  (value: unknown): ValidationResult => {
    if (value === null || value === undefined) return message;
    if (typeof value === "string" && value.trim() === "") return message;
    if (Array.isArray(value) && value.length === 0) return message;
    return null;
  };

/**
 * Validates email format
 */
export const email = (message = "Enter a valid email address (e.g., name@example.com)"): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null; // Let required handle empty
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(value.trim())) return message;
    return null;
  };

/**
 * Validates minimum length
 */
export const minLength = (min: number, message?: string): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    if (value.length < min) {
      return message || `Must be at least ${min} characters (currently ${value.length})`;
    }
    return null;
  };

/**
 * Validates maximum length
 */
export const maxLength = (max: number, message?: string): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    if (value.length > max) {
      return message || `Must be at most ${max} characters (currently ${value.length})`;
    }
    return null;
  };

/**
 * Validates that value matches another value (e.g., password confirmation)
 */
export const matches = (getValue: () => string, message = "Values do not match"): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    if (value !== getValue()) return message;
    return null;
  };

/**
 * Validates URL format
 */
export const url = (message = "Enter a valid URL starting with http:// or https://"): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    try {
      const urlObj = new URL(value);
      if (!["http:", "https:"].includes(urlObj.protocol)) {
        return message;
      }
    } catch {
      return message;
    }
    return null;
  };

/**
 * Validates DOI format
 */
export const doi = (message = "Enter a valid DOI (e.g., 10.1000/example)"): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    // DOI format: 10.xxxx/xxxx (simplified pattern)
    const doiRegex = /^10\.\d{4,}\/[^\s]+$/;
    if (!doiRegex.test(value.trim())) return message;
    return null;
  };

/**
 * Validates year format (4 digits, reasonable range)
 */
export const year = (minYear = 1800, maxYear?: number): Validator =>
  (value: unknown): ValidationResult => {
    if (value === null || value === undefined || value === "") return null;
    const currentYear = new Date().getFullYear();
    const max = maxYear || currentYear + 1;

    const numValue = typeof value === "string" ? parseInt(value, 10) : value;
    if (typeof numValue !== "number" || isNaN(numValue)) {
      return "Enter a valid 4-digit year";
    }
    if (numValue < minYear || numValue > max) {
      return `Year must be between ${minYear} and ${max}`;
    }
    return null;
  };

/**
 * Validates numeric value is within range
 */
export const numberRange = (min?: number, max?: number): Validator =>
  (value: unknown): ValidationResult => {
    if (value === null || value === undefined || value === "") return null;
    const numValue = typeof value === "string" ? parseFloat(value) : value;
    if (typeof numValue !== "number" || isNaN(numValue)) {
      return "Enter a valid number";
    }
    if (min !== undefined && numValue < min) {
      return `Value must be at least ${min}`;
    }
    if (max !== undefined && numValue > max) {
      return `Value must be at most ${max}`;
    }
    return null;
  };

/**
 * Validates date format (YYYY-MM-DD)
 */
export const dateFormat = (message = "Enter a valid date in YYYY-MM-DD format"): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRegex.test(value)) return message;

    // Check if it's a valid date
    const date = new Date(value);
    if (isNaN(date.getTime())) return message;

    return null;
  };

/**
 * Validates that a string only contains numeric characters
 */
export const numericOnly = (message = "Only numbers are allowed"): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    if (!/^\d+$/.test(value)) return message;
    return null;
  };

/**
 * Pattern matcher with custom regex
 */
export const pattern = (regex: RegExp, message: string): Validator =>
  (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;
    if (!regex.test(value)) return message;
    return null;
  };

// ============================================================================
// Password Validators
// ============================================================================

/**
 * Validates password strength with specific feedback
 */
export const passwordStrength = (options?: {
  minLength?: number;
  requireUppercase?: boolean;
  requireLowercase?: boolean;
  requireNumber?: boolean;
  requireSpecial?: boolean;
}): Validator => {
  const opts = {
    minLength: 6,
    requireUppercase: false,
    requireLowercase: false,
    requireNumber: false,
    requireSpecial: false,
    ...options
  };

  return (value: unknown): ValidationResult => {
    if (!value || typeof value !== "string") return null;

    const issues: string[] = [];

    if (value.length < opts.minLength) {
      issues.push(`at least ${opts.minLength} characters`);
    }
    if (opts.requireUppercase && !/[A-Z]/.test(value)) {
      issues.push("an uppercase letter");
    }
    if (opts.requireLowercase && !/[a-z]/.test(value)) {
      issues.push("a lowercase letter");
    }
    if (opts.requireNumber && !/\d/.test(value)) {
      issues.push("a number");
    }
    if (opts.requireSpecial && !/[!@#$%^&*(),.?":{}|<>]/.test(value)) {
      issues.push("a special character");
    }

    if (issues.length > 0) {
      return `Password needs ${issues.join(", ")}`;
    }
    return null;
  };
};

// ============================================================================
// Composite Validators
// ============================================================================

/**
 * Combines multiple validators - returns first error found
 */
export const compose = (...validators: Validator[]): Validator =>
  (value: unknown): ValidationResult => {
    for (const validator of validators) {
      const result = validator(value);
      if (result) return result;
    }
    return null;
  };

/**
 * Makes a validator optional (only runs if value is provided)
 */
export const optional = (validator: Validator): Validator =>
  (value: unknown): ValidationResult => {
    if (value === null || value === undefined || value === "") return null;
    return validator(value);
  };

// ============================================================================
// Form-level Types and Utilities
// ============================================================================

export interface FieldValidation {
  validator: Validator;
  /** When to validate: 'change' for every keystroke, 'blur' for when field loses focus */
  validateOn?: 'change' | 'blur';
  /** Debounce time in ms for 'change' validation (default: 300) */
  debounceMs?: number;
}

export type ValidationSchema<T extends Record<string, unknown>> = {
  [K in keyof T]?: FieldValidation | Validator;
};

export interface FieldState {
  value: unknown;
  error: string | null;
  touched: boolean;
  dirty: boolean;
}

export type FormErrors<T> = {
  [K in keyof T]?: string | null;
};

/**
 * Validates all fields against a schema
 */
export function validateForm<T extends Record<string, unknown>>(
  values: T,
  schema: ValidationSchema<T>
): FormErrors<T> {
  const errors: FormErrors<T> = {};

  for (const [fieldName, validation] of Object.entries(schema)) {
    if (!validation) continue;

    const validator = typeof validation === 'function'
      ? validation
      : validation.validator;

    const error = validator(values[fieldName as keyof T]);
    if (error) {
      errors[fieldName as keyof T] = error;
    }
  }

  return errors;
}

/**
 * Checks if a form has any errors
 */
export function hasErrors<T>(errors: FormErrors<T>): boolean {
  return Object.values(errors).some(error => error !== null && error !== undefined);
}

// ============================================================================
// Specific Field Validators (Pre-configured for common use cases)
// ============================================================================

export const validators = {
  email: compose(required("Email is required"), email()),
  password: compose(required("Password is required"), minLength(6)),
  confirmPassword: (getPassword: () => string) =>
    compose(required("Please confirm your password"), matches(getPassword, "Passwords do not match")),

  // Zotero-specific
  zoteroApiKey: compose(required("API Key is required"), minLength(20, "API Key should be at least 20 characters")),
  zoteroUserId: compose(required("User ID is required"), numericOnly("User ID should contain only numbers")),

  // Metadata-specific
  title: required("Title is required"),
  year: compose(optional(year(1800))),
  doi: optional(doi()),
  url: optional(url()),
  dateAccessed: optional(dateFormat()),
};
