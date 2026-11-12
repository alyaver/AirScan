const HEALTH_ENDPOINT = "/api/health";

export async function getBackendHealth(fetchImpl = fetch) {
  const response = await fetchImpl(HEALTH_ENDPOINT, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Backend health request failed with status ${response.status}.`);
  }

  const payload = await response.json();

  if (payload.status !== "ok" || payload.service !== "airscan-backend") {
    throw new Error("Backend health response did not match the AirScan API contract.");
  }

  return payload;
}