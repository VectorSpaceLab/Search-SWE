FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0

COPY install-rust.sh /tmp/install-rust.sh
RUN sh /tmp/install-rust.sh && rm /tmp/install-rust.sh
ENV PATH="/opt/rust/bin:${PATH}" CARGO_HOME=/opt/cargo
COPY starter/ /app/submission/
RUN cd /app/submission && cargo fetch --locked \
    && cargo build --release --locked --offline \
    && rm -rf target \
    && mkdir -p /task/data /task/docs /logs
WORKDIR /app/submission
ENV CARGO_TARGET_DIR=/app/build
COPY smoke.py /task/smoke.py
