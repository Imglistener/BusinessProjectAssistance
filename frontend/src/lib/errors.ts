import { ApiError } from "../api/client";

export const errorMessage = (e: unknown, fallback = "Something went wrong. Try again.") =>
  e instanceof ApiError ? e.message : fallback;
