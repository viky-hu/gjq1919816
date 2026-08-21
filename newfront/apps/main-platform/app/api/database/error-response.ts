export function toNodeDatabaseErrorResponse(err: unknown): Response {
  const message = err instanceof Error ? err.message : "未知错误";
  if (message.includes("不存在") || message.includes("无权限")) {
    return Response.json({ error: message }, { status: 404 });
  }
  return Response.json({ error: message }, { status: 500 });
}
