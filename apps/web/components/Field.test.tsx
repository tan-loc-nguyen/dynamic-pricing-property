import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Field } from "./Field";

describe("Field", () => {
  it("associates the label with its child input", () => {
    render(
      <Field label="Property name">
        <input />
      </Field>
    );
    expect(screen.getByLabelText("Property name")).toBeInTheDocument();
  });

  it("omits the hint when none is given", () => {
    const { container } = render(
      <Field label="Property name">
        <input />
      </Field>
    );
    expect(container.querySelectorAll('[data-slot="field-description"]').length).toBe(0);
  });

  it("renders the hint when given one", () => {
    render(
      <Field label="Sensitivity" hint="Higher reacts faster to pace gaps">
        <input />
      </Field>
    );
    expect(screen.getByText("Higher reacts faster to pace gaps")).toBeInTheDocument();
  });
});
