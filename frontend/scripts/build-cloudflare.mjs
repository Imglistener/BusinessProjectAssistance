// Builds the app for Cloudflare: the API is on the same address (/api), whatever VITE_API_BASE_URL the root .env
// sets for local development.
import { build } from "vite";

process.env.VITE_API_BASE_URL = "/api";
await build();
