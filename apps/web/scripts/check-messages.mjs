/**
 * Parse every message with the real ICU compiler.
 *
 * The Python guards check that keys exist, that their placeholders are
 * satisfiable, and that nothing is dead — all from outside the ICU grammar.
 * They cannot see a message that is well-formed JSON and malformed ICU, which
 * is how `'{event_name}'` shipped: the apostrophe is an ICU escape, so the
 * braces rendered literally while every other check passed.
 *
 * It does NOT supersede `test_no_message_escapes_its_own_placeholder`. An
 * escaped placeholder is well-formed ICU and compiles cleanly here, so this
 * check is blind to the very class that motivated it. The two are complements,
 * not duplicates: this one catches malformed ICU, that one catches valid ICU
 * that says the wrong thing. Keep both.
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import IntlMessageFormat from "intl-messageformat";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "messages");
const failures = [];

const walk = (node, trail, locale) => {
  for (const [key, value] of Object.entries(node)) {
    const path = trail ? `${trail}.${key}` : key;
    if (value && typeof value === "object") walk(value, path, locale);
    else {
      try {
        new IntlMessageFormat(value, locale === "vi" ? "vi-VN" : "en-US");
      } catch (error) {
        failures.push(`${locale}: ${path} — ${error.message}`);
      }
    }
  }
};

for (const file of readdirSync(dir).filter((f) => f.endsWith(".json"))) {
  const locale = file.replace(".json", "");
  walk(JSON.parse(readFileSync(join(dir, file), "utf8")), "", locale);
}

if (failures.length) {
  console.error(`ICU parse failures:\n  ${failures.join("\n  ")}`);
  process.exit(1);
}
console.log("messages: ICU parses cleanly in every locale");
