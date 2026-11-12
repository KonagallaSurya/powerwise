const authForm = document.querySelector("#auth-form");

authForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = authForm.querySelector("button[type=submit]");
  button.disabled = true;
  const original = button.innerHTML;
  button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Please wait';
  const payload = Object.fromEntries(new FormData(authForm).entries());
  try {
    const response = await fetch(`/api/auth/${authForm.dataset.auth}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content
      },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Unable to continue.");
    window.location.assign("/dashboard");
  } catch (error) {
    let toast = document.querySelector("#toast-stack");
    toast.innerHTML = "";
    const message = document.createElement("div");
    message.className = "toast-message error";
    message.textContent = error.message;
    toast.append(message);
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
});
