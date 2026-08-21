export function toChatHistoryErrorResponse(err: unknown): Response {
  const message = err instanceof Error ? err.message : "Unknown error";
  if (message.includes("Conversation not found")) {
    return Response.json({ error: "Conversation not found" }, { status: 404 });
  }
  return Response.json({ error: message }, { status: 500 });
}
