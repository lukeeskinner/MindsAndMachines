// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { TurnResponse } from "../../contracts/api";
import fixture from "../../contracts/fixtures/turn_response.json";
import { TeachingSource } from "../src/components/study/TeachingSource";

afterEach(cleanup);

describe("teaching provenance", () => {
  it.each([
    [undefined, false, "Teaching source not reported"],
    [undefined, true, "Marked fallback teaching"],
    ["authored", false, "Authored teaching"],
    ["authored_fallback", true, "Reviewed fallback"],
    ["bedrock", true, "Marked fallback teaching"],
  ])("does not infer generation from provider or prose (%s, %s)", (source, fallback, label) => {
    const result = {
      ...fixture, mode: "live", provider: "bedrock",
      tutor: { text: "Live AI from Bedrock", fallback, teaching_source: source },
    } as TurnResponse;
    render(<TeachingSource result={result} />);
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByText("AI-generated teaching")).toBeNull();
  });
});
