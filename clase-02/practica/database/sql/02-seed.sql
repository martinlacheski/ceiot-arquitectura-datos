INSERT INTO organizations (id, name) VALUES ('11111111-1111-1111-1111-111111111111', 'CEIoT Lab');
INSERT INTO users (id, email, display_name) VALUES ('22222222-2222-2222-2222-222222222222', 'student@example.edu', 'Sample Student');
INSERT INTO organization_users (organization_id, user_id, role) VALUES ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'operator');
INSERT INTO locations (id, organization_id, name, description, latitude, longitude) VALUES
('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'Laboratory A', 'Environmental test bench', -34.60370, -58.38160);
INSERT INTO devices (id, organization_id, name, serial_number, model, installed_at) VALUES
('44444444-4444-4444-4444-444444444444', '11111111-1111-1111-1111-111111111111', 'Air monitor A-01', 'CEIOT-A-01', 'Enviro-1', now());
INSERT INTO device_status_history (device_id, status, started_at) VALUES ('44444444-4444-4444-4444-444444444444', 'active', now());
INSERT INTO device_location_history (device_id, location_id, started_at) VALUES ('44444444-4444-4444-4444-444444444444', '33333333-3333-3333-3333-333333333333', now());
INSERT INTO measurements (device_id, variable, value, unit, recorded_at) VALUES
('44444444-4444-4444-4444-444444444444', 'temperature', 23.4, 'C', now() - interval '5 minutes'),
('44444444-4444-4444-4444-444444444444', 'humidity', 48.2, '%', now() - interval '4 minutes');
