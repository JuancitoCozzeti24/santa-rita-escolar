/* Read-only, fail-closed account check that does not depend on content.js.
 * chrome.scripting.executeScript serializes this function into the Classroom
 * tab. It never uses authuser query parameters, secondary account menus, cookies
 * or the Classroom page body to claim teacher identity.
 */
function probeClassroomActiveAccount(expectedEmail) {
  const expected = String(expectedEmail || "").trim().toLowerCase();
  const url = String(location.href || "");
  if (!expected) return {ok: null, reason: "missing_expected_email", detectedEmails: [], url};
  if (location.origin !== "https://classroom.google.com") {
    return {ok: null, reason: "not_classroom_origin", detectedEmails: [], url};
  }

  const selectors = [
    '[aria-label^="Cuenta de Google"]', '[aria-label^="Google Account"]',
    '[aria-label*="Cuenta de Google:"]', '[aria-label*="Google Account:"]',
    '[title^="Cuenta de Google"]', '[title^="Google Account"]',
    '[data-tooltip^="Cuenta de Google"]', '[data-tooltip^="Google Account"]',
  ].join(",");
  const pattern = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig;
  const emails = new Set();
  for (const control of document.querySelectorAll(selectors)) {
    const rect = control.getBoundingClientRect();
    const style = getComputedStyle(control);
    if (
      rect.width <= 0 || rect.height <= 0 ||
      style.display === "none" || style.visibility === "hidden" ||
      rect.top < -10 || rect.top > 180 ||
      rect.left < Math.max(0, innerWidth * 0.45)
    ) continue;
    const values = [
      control.getAttribute("aria-label"), control.getAttribute("title"),
      control.getAttribute("data-tooltip"), control.getAttribute("data-email"),
    ];
    for (const value of values) {
      for (const match of String(value || "").matchAll(pattern)) {
        emails.add(String(match[0]).toLowerCase());
      }
    }
  }

  const detectedEmails = [...emails];
  if (detectedEmails.includes(expected)) {
    return {ok: true, expectedEmail: expected, detectedEmails, url};
  }
  if (detectedEmails.length) {
    return {ok: false, expectedEmail: expected, detectedEmails, url};
  }
  return {
    ok: null, expectedEmail: expected, detectedEmails: [],
    reason: document.readyState === "loading" ? "classroom_loading" : "active_account_not_visible",
    url,
  };
}
