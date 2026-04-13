// Read the CSRF token from the URL query on launch and remember it for the
// session. The server minted this token and sent it in the launch URL;
// every mutating request must carry it in the X-Understudy-CSRF header.

const urlToken = new URLSearchParams(window.location.search).get("t");
// Keep in memory only — never in localStorage. Clearing it is a page reload.
export const CSRF_TOKEN: string = urlToken ?? "";

if (!CSRF_TOKEN) {
  console.warn("no CSRF token in URL; mutating API calls will be refused.");
}
