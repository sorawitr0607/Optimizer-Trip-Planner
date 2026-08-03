export interface Trip {
  trip_id: string;
  name: string;
  destination: string;
  planning_mode: "explore_first" | "ready_to_schedule";
  language: "en" | "th";
  created_at: string;
}

export type StageKey = "setup" | "places" | "evidence" | "optimize" | "itinerary";

export interface JourneyStage {
  key: StageKey;
  done: boolean;
  blocked_by: StageKey | null;
}

export interface Journey {
  stages: JourneyStage[];
  next: StageKey;
  capability_gaps: string[];
  has_active_plan: boolean;
  choice_count: number;
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly detail: unknown,
  ) {
    super(code);
  }
}

export async function rpc<T>(method: string, payload: Record<string, unknown> = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const response = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const value = (await response.json()) as T | { code?: string; detail?: unknown };
    if (!response.ok) {
      const error = value as { code?: string; detail?: unknown };
      throw new ApiError(error.code ?? "internal_error", error.detail);
    }
    return value as T;
  } finally {
    clearTimeout(timeout);
  }
}
