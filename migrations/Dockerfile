# Dockerfile
FROM --platform=$BUILDPLATFORM postgres:16-alpine AS builder

# Download AWS RDS certificate
RUN wget -O /etc/ssl/certs/rds-ca-2019-root.pem \
    https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

# Final stage
FROM --platform=$TARGETPLATFORM postgres:16-alpine

WORKDIR /migrations

# Copy certificate from builder
COPY --from=builder /etc/ssl/certs/rds-ca-2019-root.pem /etc/ssl/certs/

# Copy migration scripts
COPY migrations/*.sql /migrations/
COPY run-migrations.sh /migrations/

# Make the script executable and ensure proper line endings
RUN chmod +x /migrations/run-migrations.sh && \
    dos2unix /migrations/run-migrations.sh 2>/dev/null || true

# Set environment variables with defaults
ENV PGPORT="5432"
ENV RDS_ENDPOINT=""
ENV PGUSER=""
ENV PGPASSWORD=""
ENV KEYCLOAK_PASSWORD=""
ENV PGSSLMODE="verify-full"
ENV PGSSLROOTCERT="/etc/ssl/certs/rds-ca-2019-root.pem"

ENTRYPOINT ["sh"]
CMD ["/migrations/run-migrations.sh"]