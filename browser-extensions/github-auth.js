/* Resolve GitHub Actions artifact links through the user's signed-in browser session.
 * Browser-managed cookies are sent by fetch; this code never reads or exports cookies. */
async function fdmxResolveBrowserAuthenticatedUrl(inputUrl) {
  let source;
  try { source = new URL(inputUrl); } catch (_) { return {url: inputUrl, browserSession: false}; }
  const match = source.hostname.toLowerCase() === "github.com"
    ? source.pathname.match(/^\/([^/]+)\/([^/]+)\/actions\/runs\/(\d+)\/artifacts\/(\d+)\/?$/)
    : null;
  if (!match) return {url: inputUrl, browserSession: false};

  const [, owner, repo, runId, artifactId] = match;
  const downloadUrl = `https://github.com/${owner}/${repo}/actions/runs/${runId}/artifacts/${artifactId}/download`;
  let response;
  try {
    response = await fetch(downloadUrl, {
      method: "GET",
      credentials: "include",
      redirect: "follow",
      cache: "no-store",
      headers: {"Accept": "application/zip, application/octet-stream;q=0.9, */*;q=0.8"}
    });
  } catch (error) {
    throw new Error("Could not use the signed-in GitHub browser session: " + error.message);
  }

  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  let finalUrl = "";
  try { finalUrl = response.url || ""; } catch (_) {}
  const finalHost = (() => { try { return new URL(finalUrl).hostname.toLowerCase(); } catch (_) { return ""; } })();
  if (!response.ok || !finalUrl || !finalHost
      || finalHost === "github.com" || finalHost === "api.github.com"
      || contentType.includes("text/html")
      || !(contentType.includes("zip") || contentType.includes("octet-stream"))) {
    try { if (response.body) await response.body.cancel(); } catch (_) {}
    throw new Error("GitHub did not return an authenticated artifact download. Check that this browser is signed in and the artifact is still available.");
  }

  // Keep only the short-lived signed object URL. Never read or forward browser cookies.
  try { if (response.body) await response.body.cancel(); } catch (_) {}
  return {url: finalUrl, browserSession: true};
}
