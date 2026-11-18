const LIVE_SOCKET_PATH = "/api/live";

export function getLiveSocketUrl(locationImpl = window.location) {
  const protocol = locationImpl.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${locationImpl.host}${LIVE_SOCKET_PATH}`;
}

export function createLiveSocket({
  WebSocketImpl = WebSocket,
  locationImpl = window.location,
  onMessage,
  onOpen,
  onClose,
  onError,
}) {
  const socket = new WebSocketImpl(getLiveSocketUrl(locationImpl));
  socket.addEventListener("message", onMessage);
  socket.addEventListener("open", onOpen);
  socket.addEventListener("close", onClose);
  socket.addEventListener("error", onError);
  return socket;
}