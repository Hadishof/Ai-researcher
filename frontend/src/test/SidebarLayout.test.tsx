// The sidebar on wide screens: collapse and bring back, resize, and remembering both.
// (jsdom has no screen size, so App sees a wide screen; the drawer is tested elsewhere.)

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "../App";
import { mockApi } from "./fakeBackend";

async function renderApp() {
  mockApi();
  const user = userEvent.setup();
  const view = render(<App />);
  await screen.findByRole("button", { name: "Collapse sidebar" });
  const app = view.container.querySelector(".app") as HTMLElement;
  return { user, app, view };
}

describe("Collapsing the sidebar", () => {
  it("collapses, shows the button that brings it back, and moves the focus to it", async () => {
    const { user, app } = await renderApp();

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    expect(app).toHaveClass("sidebar-collapsed");
    const openButton = screen.getByRole("button", { name: "Open sidebar" });
    expect(openButton).toHaveClass("menu-button-visible");
    expect(openButton).toHaveFocus(); // keyboard users are not sent back to the top of the page

    await user.click(openButton);

    expect(app).not.toHaveClass("sidebar-collapsed");
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toHaveFocus();
  });

  it("remembers the collapsed state after a reload", async () => {
    const first = await renderApp();
    await first.user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    first.view.unmount();

    const second = await renderApp(); // like reloading the page

    expect(second.app).toHaveClass("sidebar-collapsed");
  });
});

describe("Resizing the sidebar", () => {
  it("resizes with the arrow keys, within the minimum and maximum", async () => {
    const { user, app } = await renderApp();
    const handle = screen.getByRole("separator", { name: "Resize sidebar" });
    expect(handle).toHaveAttribute("aria-valuenow", "288");

    handle.focus();
    await user.keyboard("{ArrowRight}");
    expect(handle).toHaveAttribute("aria-valuenow", "304");
    expect(app.style.getPropertyValue("--sidebar-chosen-width")).toBe("304px");

    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(handle).toHaveAttribute("aria-valuenow", "272");

    await user.keyboard("{End}");
    expect(handle).toHaveAttribute("aria-valuenow", "480");
    await user.keyboard("{ArrowRight}"); // already at the maximum
    expect(handle).toHaveAttribute("aria-valuenow", "480");

    await user.keyboard("{Home}");
    expect(handle).toHaveAttribute("aria-valuenow", "220");
  });

  it("resizes by dragging the handle", async () => {
    await renderApp();
    const handle = screen.getByRole("separator", { name: "Resize sidebar" });

    fireEvent.pointerDown(handle, { clientX: 288, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 350, pointerId: 1 });
    fireEvent.pointerUp(handle, { pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 400, pointerId: 1 }); // after letting go: no change

    expect(handle).toHaveAttribute("aria-valuenow", "350");
  });

  it("remembers the width after a reload", async () => {
    const first = await renderApp();
    screen.getByRole("separator", { name: "Resize sidebar" }).focus();
    await first.user.keyboard("{ArrowRight}");
    first.view.unmount();

    await renderApp();
    expect(screen.getByRole("separator", { name: "Resize sidebar" })).toHaveAttribute("aria-valuenow", "304");
  });

  it("keeps a saved width within the limits", async () => {
    localStorage.setItem("sidebar-width", "9999");
    await renderApp();
    expect(screen.getByRole("separator", { name: "Resize sidebar" })).toHaveAttribute("aria-valuenow", "480");
  });
});

describe("Blocked storage", () => {
  it("still works when localStorage throws (it is just not remembered)", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { user, app } = await renderApp();

    expect(screen.getByRole("separator", { name: "Resize sidebar" })).toHaveAttribute("aria-valuenow", "288");
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(app).toHaveClass("sidebar-collapsed");
  });
});
