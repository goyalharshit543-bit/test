/* Login page logic */
(function () {
  const form = document.getElementById("login-form");
  const errBox = document.getElementById("login-error");
  const btn = document.getElementById("login-btn");

  // Already signed in? Verify the token and jump to the dashboard.
  if (API.token()) {
    API.get("/api/auth/me")
      .then(() => (window.location.href = "/dashboard"))
      .catch(() => API.clearToken());
  }

  // Clickable demo credentials
  document.querySelectorAll(".demo-cred").forEach((b) => {
    b.addEventListener("click", () => {
      document.getElementById("email").value = b.dataset.email;
      document.getElementById("password").value = b.dataset.password;
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.classList.add("hidden");
    btn.disabled = true;
    btn.textContent = "Signing in…";
    try {
      const res = await API.post("/api/auth/login", {
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value,
      });
      API.setToken(res.token);
      window.location.href = "/dashboard";
    } catch (err) {
      errBox.textContent = err.message || "Login failed";
      errBox.classList.remove("hidden");
      btn.disabled = false;
      btn.textContent = "Sign in";
    }
  });
})();
