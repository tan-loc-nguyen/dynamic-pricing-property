import { inputClassName } from "@/components/ui/input";

/**
 * Native <select> has no shadcn wrapper in this preset (only Input styles
 * <input>), so this reuses Input's actual class list to keep selects and
 * inputs looking consistent -- and to stay in sync automatically if Input's
 * styling ever changes, rather than drifting as a hand-copied duplicate.
 * The file:* classes in there are no-ops on a <select>, which is harmless.
 */
export const selectClass = inputClassName;
