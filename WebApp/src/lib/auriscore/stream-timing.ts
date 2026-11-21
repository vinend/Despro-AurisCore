// Cloud PCM may wait in the device's bounded queue during a brief network stall.
// Actual socket disconnects and discontinuous samples still invalidate a session.
export const LAN_AUDIO_STALL_MS = 2000;
export const CLOUD_AUDIO_STALL_MS = 7000;
