-- =============================================================
-- Seed data — run after schema.sql
-- =============================================================

-- Roles
INSERT INTO roles (name, description) VALUES
    ('admin', 'Full system access'),
    ('user', 'Standard user access')
ON CONFLICT (name) DO NOTHING;

-- Permissions
INSERT INTO permissions (name, description) VALUES
    ('users:read', 'View user information'),
    ('users:write', 'Create and modify users'),
    ('items:read', 'View items'),
    ('items:write', 'Create and modify items'),
    ('items:delete', 'Delete items')
ON CONFLICT (name) DO NOTHING;

-- Admin gets all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'admin'
ON CONFLICT DO NOTHING;

-- User gets read permissions + items:write
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'user' AND p.name IN ('users:read', 'items:read', 'items:write')
ON CONFLICT DO NOTHING;

-- Admin user (password: admin123)
-- Argon2 hash of 'admin123'
INSERT INTO users (email, username, password_hash, full_name, is_active) VALUES
    ('admin@example.com', 'admin',
     '$argon2id$v=19$m=65536,t=2,p=2$Ki3mTyM4WGrMR8/EOYAk5A$lr/vxvqPXlbXVWaDO8TsdzRvD7OiMKawav8zXME9XPg',
     'Administrator', TRUE)
ON CONFLICT DO NOTHING;

-- Assign admin role
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'admin'
ON CONFLICT DO NOTHING;

-- Sample items (50) for pagination testing
INSERT INTO items (name, description, category, priority, is_active, owner_id, created_at)
SELECT
    'Item ' || lpad(i::text, 3, '0'),
    'Description for item ' || i,
    (ARRAY['electronics','furniture','books','clothing','sports'])[1 + (i % 5)],
    (i * 7) % 5,  -- priority 0..4 distributed
    i % 7 != 0,
    (SELECT id FROM users WHERE username = 'admin'),
    now() - ((50 - i) || ' hours')::interval
FROM generate_series(1, 50) AS i;

-- Scheduled jobs
INSERT INTO scheduled_jobs (job_name, description, interval_seconds, next_run_at)
VALUES ('heartbeat_check', 'Example job: logs worker identity every 5 minutes', 300, now())
ON CONFLICT (job_name) DO NOTHING;
