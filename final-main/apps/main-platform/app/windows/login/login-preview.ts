// Temporary local preview path; production builds always keep the real auth gate.
export const ENABLE_EMPTY_LOGIN_PREVIEW = process.env.NODE_ENV !== "production";

export function shouldUseEmptyLoginPreview(account: string, password: string) {
  return ENABLE_EMPTY_LOGIN_PREVIEW && account.trim() === "" && password === "";
}
