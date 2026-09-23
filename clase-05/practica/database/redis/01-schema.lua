-- Redis has no server-side schema. This hash records the canonical key contract.
redis.call("HSET", "lab:schema:device_current",
  "pattern", "device:<device_id>:<purpose>",
  "purposes", "state,last_measurement,last_seen,presence",
  "presence_policy", "expiring",
  "source_of_truth", "reconstructible_projection")
return "schema-ready"
