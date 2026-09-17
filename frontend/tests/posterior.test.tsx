// @vitest-environment jsdom
import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { BetaDistributionPlot, betaCurve } from "../src/components/study/BetaDistributionPlot";
afterEach(cleanup);
const prior = { concept_id: "power", alpha: 1, beta: 1, mean: .5,
  interval90: { lower: .05, upper: .95 }, evidence_count: 0 };
test("uniform prior has constant density and trusted interval text", () => {
  expect(betaCurve(1,1).every(p => p.y === 1)).toBe(true);
  render(<BetaDistributionPlot current={prior}/>);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Beta(1, 1); mean 50.0%; 90% interval 5.0% to 95.0%; 0 observations");
});
test("known Beta density and mean marker are correct", () => {
  const points=betaCurve(2,2);
  expect(points.find(p=>p.x===.5)?.y).toBeCloseTo(1.5,8);
  render(<BetaDistributionPlot current={{...prior,alpha:2,beta:1,mean:2/3,
    interval90:{lower:.2236,upper:.9747},evidence_count:1}} before={prior}/>);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("66.7%");
  expect(screen.getByText(/Dashed: session start/)).toBeTruthy();
  expect(document.querySelector("svg")?.innerHTML).not.toMatch(/NaN|Infinity/);
});
test("concentrated and boundary distributions remain finite", () => {
  for(const [a,b] of [[2000,2000],[1,5000],[5000,1],[1,1]]) {
    const points=betaCurve(a,b);
    expect(points.length).toBeGreaterThan(160);
    expect(points.every(p=>Number.isFinite(p.y))).toBe(true);
    expect(Math.max(...points.map(p=>p.y))).toBeGreaterThan(0);
  }
});
test("missing or invalid posterior parameters never get inferred from rounded means", () => {
  expect(betaCurve(0,1)).toEqual([]);
  expect(betaCurve(NaN,2)).toEqual([]);
  const {container}=render(<BetaDistributionPlot current={{...prior,alpha:undefined,beta:undefined}}/>);
  expect(container.querySelector("svg")).toBeNull();
});
