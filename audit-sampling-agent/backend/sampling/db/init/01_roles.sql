-- Application role: connects without BYPASSRLS so row-level security is
-- actually enforced (never rely on the app remembering to filter by tenant).
CREATE ROLE app_role LOGIN PASSWORD 'app_role_dev_password' NOBYPASSRLS;
GRANT CONNECT ON DATABASE audit_sampling TO app_role;
GRANT USAGE ON SCHEMA public TO app_role;

-- Table-level grants are applied per-table by Alembic migrations (so a new
-- migration can grant/revoke without editing this bootstrap script), except
-- ALTER DEFAULT PRIVILEGES here so future tables inherit the same base grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_role;
