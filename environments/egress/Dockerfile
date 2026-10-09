# Use scripts/build_egress_gateway.py; it stages and verifies pinned APKs.
ARG COMPONENT_IMAGE=searchswe-egress-component:build-required
FROM ${COMPONENT_IMAGE}
ARG GATEWAY_SOURCE_SHA
ARG RUNTIME_LOCK_SHA
COPY packages/ /tmp/searchswe-apks/
RUN apk add --no-cache --no-network --repositories-file /dev/null /tmp/searchswe-apks/*.apk && rm -rf /tmp/searchswe-apks
COPY runtime.lock.json /usr/share/searchswe-egress/runtime.json
COPY gateway.py /opt/searchswe/gateway.py
COPY --chmod=755 entrypoint.sh /opt/egress-sidecar/entrypoint.sh
COPY --chmod=755 network-policy /usr/local/bin/network-policy
LABEL org.search-swe.egress.gateway="1"
LABEL org.search-swe.egress.source-sha256=${GATEWAY_SOURCE_SHA}
LABEL org.search-swe.egress.runtime-lock-sha256=${RUNTIME_LOCK_SHA}
