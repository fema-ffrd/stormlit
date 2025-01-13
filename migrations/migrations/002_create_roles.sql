-- Create roles if they don't exist
SELECT 'CREATE ROLE keycloak LOGIN PASSWORD ' || quote_literal(:'keycloak_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak')\gexec

SELECT 'CREATE ROLE streamlit LOGIN PASSWORD ' || quote_literal(:'streamlit_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'streamlit')\gexec