import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecordingStatus } from "./RecordingStatus.jsx";

describe("RecordingStatus", () => {
  it("clearly distinguishes inactive recording from live monitoring", () => {
    render(<RecordingStatus />);

    expect(screen.getByTestId("recording-state")).toHaveTextContent("Inactive");
    expect(
      screen.getByText("Live monitoring is active independently; scan observations are not being saved."),
    ).toBeInTheDocument();
  });
});