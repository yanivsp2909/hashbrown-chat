// 🔐 Log in / create account.

import { $ } from "./dom.js";

const form = $("login-form");
const user = $("login-user");
const pass = $("login-pass");
const pass2 = $("login-pass2");
const submit = $("login-submit");
const error = $("login-error");
let mode = "login";

function setMode(next) {
  mode = next;
  const register = mode === "register";
  $("tab-login").setAttribute("aria-selected", String(!register));
  $("tab-register").setAttribute("aria-selected", String(register));
  $("repeat-field").hidden = !register;
  $("login-hint").hidden = !register;
  pass.autocomplete = register ? "new-password" : "current-password";
  submit.textContent = register ? "Create account 🥔" : "Log in 🍟";
  showLoginError("");
}

export function showLoginError(text) {
  error.textContent = text;
  error.hidden = !text;
  setBusy(false);
}

export function setBusy(busy) {
  submit.disabled = busy;
  submit.setAttribute("aria-busy", String(busy));
  submit.textContent = busy ? "Checking…" : mode === "register" ? "Create account 🥔" : "Log in 🍟";
}

export function focusLogin() {
  (user.value ? pass : user).focus();
}

function check(username, password) {
  if (!username) return "Type your username.";
  if (mode === "register" && !/^(?:[A-Za-z0-9_]{3,16}|[\u05d0-\u05ea0-9_]{3,16})$/u.test(username)) {
    return "Usernames are 3–16 English or Hebrew letters (not both), digits or _.";
  }
  if (password.length < 4 || password.length > 64) return "Passwords are 4–64 characters.";
  if (mode === "register" && pass2.value !== password) return "The two passwords don't match.";
  return null;
}

/** onSubmit(action, username, password) sends the login; the reply arrives as an auth_result. */
export function initLogin({ onSubmit }) {
  $("tab-login").addEventListener("click", () => setMode("login"));
  $("tab-register").addEventListener("click", () => setMode("register"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const username = user.value.trim();
    const problem = check(username, pass.value);
    const bad = !problem ? null : /user/i.test(problem) ? user : /match/i.test(problem) ? pass2 : pass;
    for (const field of [user, pass, pass2]) field.toggleAttribute("aria-invalid", field === bad);
    if (problem) {
      showLoginError(problem);
      bad.focus();
      return;
    }
    showLoginError("");
    setBusy(true);
    onSubmit(mode, username, pass.value);
  });
}

export function clearPasswords() {
  pass.value = "";
  pass2.value = "";
}
