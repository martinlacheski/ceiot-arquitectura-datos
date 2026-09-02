-- 1. Devices and their current location.
SELECT d.name, d.serial_number, l.name AS current_location
FROM devices d
LEFT JOIN device_location_history h ON h.device_id = d.id AND h.ended_at IS NULL
LEFT JOIN locations l ON l.id = h.location_id
ORDER BY d.name;

-- 2. Measurement history, newest first.
SELECT d.name, m.variable, m.value, m.unit, m.recorded_at
FROM measurements m JOIN devices d ON d.id = m.device_id
ORDER BY m.recorded_at DESC;

-- 3. Device status history.
SELECT d.name, h.status, h.started_at, h.ended_at
FROM device_status_history h JOIN devices d ON d.id = h.device_id
ORDER BY h.started_at DESC;
