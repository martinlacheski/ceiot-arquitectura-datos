local ttl = tonumber(ARGV[1])
if not ttl or ttl < 1 or ttl ~= math.floor(ttl) then
  return redis.error_reply("presence TTL must be a positive integer")
end

local devices = {
  {
    id = "AMB-001",
    state = "ONLINE",
    measurement = '{"temperature":24.6,"humidity":48.2,"measured_at":"2025-05-12T10:32:00Z"}',
    last_seen = "2025-05-12T10:32:04Z"
  },
  {
    id = "AIR-002",
    state = "ONLINE",
    measurement = '{"temperature":24.6,"humidity":47.8,"co2":812,"measured_at":"2025-05-12T10:32:00Z"}',
    last_seen = "2025-05-12T10:32:03Z"
  },
  {
    id = "ACT-003",
    state = "IDLE",
    measurement = '{"ventilation_state":"OFF","measured_at":"2025-05-12T10:32:00Z"}',
    last_seen = "2025-05-12T10:32:02Z"
  }
}

for _, device in ipairs(devices) do
  local prefix = "device:" .. device.id .. ":"
  redis.call("SET", prefix .. "state", device.state)
  redis.call("SET", prefix .. "last_measurement", device.measurement)
  redis.call("SET", prefix .. "last_seen", device.last_seen)
  redis.call("SET", prefix .. "presence", "ONLINE", "EX", ttl)
end

return #devices
