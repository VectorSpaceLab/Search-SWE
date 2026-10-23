FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0
RUN useradd --create-home --uid 10001 --user-group submission
COPY . /tests/
COPY build_driver.py /task/tools/build_driver.py
RUN mkdir -m 700 /task-run && chmod 700 /tests /tests/test.sh && chmod -R a+rX /task/tools
