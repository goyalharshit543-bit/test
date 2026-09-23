/* Tiny fetch wrapper: attaches the JWT, parses JSON, handles auth errors. */
window.API = {
  token() {
    return localStorage.getItem("sc_token") || "";
  },
  setToken(t) {
    localStorage.setItem("sc_token", t);
  },
  clearToken() {
    localStorage.removeItem("sc_token");
  },

  async req(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = this.token();
    if (token) headers["Authorization"] = "Bearer " + token;

    const res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (res.status === 401 && path !== "/api/auth/login") {
      this.clearToken();
      window.location.href = "/";
      throw new Error("Session expired — please sign in again");
    }

    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      /* non-JSON response */
    }
    if (!res.ok) {
      const detail =
        data && (data.detail || data.message)
          ? typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail)
          : res.status + " " + res.statusText;
      throw new Error(detail);
    }
    return data;
  },

  get(path) {
    return this.req(path);
  },
  post(path, body) {
    return this.req(path, { method: "POST", body });
  },
  patch(path, body) {
    return this.req(path, { method: "PATCH", body });
  },
};

/* WebSocket URL helper with auth token */
window.wsURL = function (path) {
  const proto = location.protocol === "https:" ? "wss://" : "ws://";
  return proto + location.host + path + "?token=" + encodeURIComponent(API.token());
};
