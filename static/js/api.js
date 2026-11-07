/* 统一请求封装：JSON 收发与错误提示规整 */

export async function requestJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    // 非 JSON 响应（例如网关错误页）
  }
  if (!response.ok) {
    const raw = typeof data.detail === "string" ? data.detail : "请求失败";
    const detail = raw.replace(/\\n/g, "\n").split("\n")[0].slice(0, 160);
    throw new Error(`${detail}（HTTP ${response.status}）`);
  }
  return data;
}
