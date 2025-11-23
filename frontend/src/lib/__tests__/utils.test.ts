import { describe, it, expect } from "vitest";
import { cn } from "../utils";

describe("cn utility function", () => {
  it("merges class names correctly", () => {
    const result = cn("text-red-500", "bg-blue-500");
    expect(result).toContain("text-red-500");
    expect(result).toContain("bg-blue-500");
  });

  it("handles conditional classes", () => {
    const isActive = true;
    const result = cn("base-class", isActive && "active-class");
    expect(result).toContain("base-class");
    expect(result).toContain("active-class");
  });

  it("removes falsy values", () => {
    const result = cn("base-class", false && "hidden", null, undefined, "visible");
    expect(result).toContain("base-class");
    expect(result).toContain("visible");
    expect(result).not.toContain("hidden");
  });

  it("handles Tailwind CSS conflicts correctly", () => {
    // twMerge should handle conflicting Tailwind classes
    const result = cn("px-2 py-1", "px-4");
    // Should keep px-4 and py-1 (later px value wins)
    expect(result).toContain("px-4");
    expect(result).toContain("py-1");
    expect(result).not.toContain("px-2");
  });

  it("merges multiple class arrays", () => {
    const result = cn(["text-sm", "font-bold"], ["text-blue-500"]);
    expect(result).toContain("text-sm");
    expect(result).toContain("font-bold");
    expect(result).toContain("text-blue-500");
  });

  it("handles empty inputs", () => {
    const result = cn();
    expect(result).toBe("");
  });

  it("handles single class name", () => {
    const result = cn("single-class");
    expect(result).toBe("single-class");
  });

  it("handles objects with boolean values", () => {
    const result = cn({
      "base-class": true,
      "active-class": true,
      "hidden-class": false,
    });
    expect(result).toContain("base-class");
    expect(result).toContain("active-class");
    expect(result).not.toContain("hidden-class");
  });

  it("combines clsx and twMerge functionality", () => {
    const isDisabled = false;
    const result = cn(
      "bg-blue-500 text-white",
      "bg-red-500", // Should override bg-blue-500
      isDisabled && "opacity-50"
    );
    expect(result).toContain("bg-red-500");
    expect(result).not.toContain("bg-blue-500");
    expect(result).toContain("text-white");
    expect(result).not.toContain("opacity-50");
  });

  it("handles complex nested conditions", () => {
    const variant = "primary";
    const size = "lg";
    const result = cn(
      "base",
      variant === "primary" && "bg-blue-500",
      size === "lg" && "px-6 py-3"
    );
    expect(result).toContain("base");
    expect(result).toContain("bg-blue-500");
    expect(result).toContain("px-6");
    expect(result).toContain("py-3");
  });
});
