/* Seeded usability defects are intentional; see SEEDED_ISSUES.json. */
(() => {
  "use strict";
  const page = document.body.dataset.page;
  const read = (key, fallback = null) => {
    try { return JSON.parse(sessionStorage.getItem(`ss_${key}`)) ?? fallback; }
    catch { return fallback; }
  };
  const save = (key, value) => sessionStorage.setItem(`ss_${key}`, JSON.stringify(value));
  const go = (file) => { window.location.href = file; };
  const plan = read("plan");
  const details = read("details");
  const payments = read("payments", []);
  const needsPlan = ["details", "verify", "review", "pay", "confirmed"].includes(page);
  const needsDetails = ["verify", "review", "pay", "confirmed"].includes(page);
  const needsVerified = ["review", "pay", "confirmed"].includes(page);
  if ((needsPlan && !["Basic", "Family Floater", "Senior Care"].includes(plan)) ||
      (needsDetails && (!details || !["name", "mobile", "pin", "dob"].every(key => typeof details[key] === "string" && details[key]))) ||
      (needsVerified && read("verified") !== true) ||
      (page === "confirmed" && (!Array.isArray(payments) || !payments.length))) {
    document.querySelector("main").innerHTML = '<section class="panel"><h1>Session expired. Start again</h1><a href="index.html">Start again</a></section>';
    return;
  }
  document.querySelectorAll("[data-plan-name]").forEach(node => { node.textContent = plan; });
  document.querySelectorAll("[data-detail]").forEach(node => { node.textContent = details[node.dataset.detail]; });
  document.querySelectorAll("[data-plan]").forEach(button => {
    button.addEventListener("click", () => {
      save("plan", button.dataset.plan);
      save("verified", false);
      save("payments", []);
      go("details.html");
    });
  });
  if (page === "explore") {
    document.getElementById("advisor").addEventListener("click", () => {
      document.getElementById("advisor-message").hidden = false;
    });
  }
  if (page === "details") {
    const form = document.getElementById("details-form");
    if (details) Object.entries(details).forEach(([key, value]) => {
      if (form.elements.namedItem(key)) form.elements.namedItem(key).value = value;
    });
    const adultDOB = value => {
      const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
      if (!match) return false;
      const [, day, month, year] = match.map(Number);
      const birthday = new Date(year, month - 1, day);
      if (birthday.getFullYear() !== year || birthday.getMonth() !== month - 1 || birthday.getDate() !== day) return false;
      const today = new Date();
      const beforeBirthday = today.getMonth() < month - 1 || (today.getMonth() === month - 1 && today.getDate() < day);
      return today.getFullYear() - year - Number(beforeBirthday) >= 18;
    };
    form.addEventListener("submit", event => {
      event.preventDefault();
      const entered = Object.fromEntries(new FormData(form));
      // D4: deliberately count digits instead of requiring a ten-digit mobile.
      const valid = entered.name.trim() && (entered.mobile.match(/\d/g) || []).length >= 5 &&
        /^\d{6}$/.test(entered.pin) && adultDOB(entered.dob);
      document.getElementById("details-error").hidden = Boolean(valid);
      if (!valid) return; // D5: a single generic error; no field highlighting.
      save("details", entered);
      save("verified", false);
      go("verify.html");
    });
  }
  if (page === "verify") {
    let otpTimer;
    document.getElementById("send-otp").addEventListener("click", () => {
      // D6: leave the page and enabled button unchanged throughout the delay.
      clearTimeout(otpTimer);
      otpTimer = setTimeout(() => {
        const digits = details.mobile.replace(/\D/g, "");
        document.getElementById("otp-message").textContent = `OTP sent to +91 ••••••${digits.slice(-2)}`;
        document.getElementById("otp-step").hidden = false;
      }, 3000);
    });
    document.getElementById("otp-form").addEventListener("submit", event => {
      event.preventDefault();
      if (document.getElementById("otp").value !== "123456") {
        document.getElementById("otp-error").hidden = false;
        return;
      }
      save("verified", true);
      go("review.html");
    });
  }
  if (page === "review") document.getElementById("confirm").addEventListener("click", () => go("pay.html"));
  if (page === "pay") {
    document.getElementById("proceed").addEventListener("click", () => {
      // D11: intentionally neither disable the button nor deduplicate submissions.
      const records = read("payments", []);
      records.push({ n: records.length + 1, amount: 4812 });
      save("payments", records);
      save("consent", document.getElementById("consent").checked);
      setTimeout(() => go("confirmed.html"), 1500);
    });
  }
  if (page === "confirmed") {
    payments.forEach(payment => {
      const row = document.createElement("li");
      row.dataset.testid = "payment-line";
      row.textContent = `Payment ${payment.n}: ₹${payment.amount.toLocaleString("en-IN")} — successful`;
      document.getElementById("payments").append(row);
    });
  }
})();
