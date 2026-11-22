import axios from "axios";
import { attachInterceptors } from "./apiClient";

const auth_api = attachInterceptors(
  axios.create({
    baseURL: "/",
  })
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username, password) =>
  auth_api.post("auth/token/", { username, password }).then((r) => r.data);