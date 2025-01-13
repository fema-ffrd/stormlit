SELECT 'CREATE ROLE keycloak LOGIN PASSWORD ' || quote_literal(:'keycloak_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak')\gexec
