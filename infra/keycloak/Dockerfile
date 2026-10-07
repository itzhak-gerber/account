# syntax=docker/dockerfile:1
# Keycloak for Azure: optimized build with the Hebrew theme and the production realm.
# Runtime settings (database, hostname, secrets, mail server) come from the environment.
ARG KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:26.4

FROM ${KEYCLOAK_IMAGE} AS builder
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=false
COPY themes/invoice /opt/keycloak/themes/invoice
RUN /opt/keycloak/bin/kc.sh build

FROM ${KEYCLOAK_IMAGE}
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY realm-invoice.json /opt/keycloak/data/import/realm-invoice.json
ENV KC_HTTP_ENABLED=true \
    KC_PROXY_HEADERS=xforwarded
EXPOSE 8080 9000
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
# --import-realm only creates the realm on first start; later changes go through the admin
# console or kcadm (the realm file is not re-applied).
CMD ["start", "--optimized", "--import-realm"]
