SELECT 'CREATE DATABASE keycloak'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec

SELECT 'CREATE DATABASE streamlit'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'streamlit')\gexec