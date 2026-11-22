/**
 * Robust loader wrapper that handles network flickers (ERR_HTTP2_PING_FAILED)
 * and deployment chunk rotation (ChunkLoadError).
 * Retries up to `maxRetries` times with backoff, and automatically reloads the page once
 * if a new deployment has superseded the cached chunks.
 */
export function withRetry<T>(loader: () => Promise<T>, maxRetries = 2): () => Promise<T> {
  return () =>
    new Promise<T>((resolve, reject) => {
      let attempts = 0;

      const execute = () => {
        loader()
          .then((comp) => {
            if (typeof window !== "undefined") {
              sessionStorage.removeItem("mil:chunk_reload_lock");
            }
            resolve(comp);
          })
          .catch((err) => {
            attempts++;
            const errMsg = String(err?.message || "");
            const isChunkOrNetworkError =
              err?.name === "ChunkLoadError" ||
              errMsg.includes("Loading chunk") ||
              errMsg.includes("Failed to fetch") ||
              errMsg.includes("ERR_HTTP2") ||
              errMsg.includes("NetworkError");

            if (attempts <= maxRetries && isChunkOrNetworkError) {
              setTimeout(execute, attempts * 800);
            } else if (isChunkOrNetworkError && typeof window !== "undefined") {
              const reloadKey = "mil:chunk_reload_lock";
              const lastReload = sessionStorage.getItem(reloadKey);
              const now = Date.now();

              // Auto-reload once if not reloaded in the last 15 seconds
              if (!lastReload || now - parseInt(lastReload, 10) > 15000) {
                sessionStorage.setItem(reloadKey, String(now));
                window.location.reload();
                return;
              }
              reject(err);
            } else {
              reject(err);
            }
          });
      };

      execute();
    });
}

export default withRetry;
