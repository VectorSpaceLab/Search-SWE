FROM docker.io/hanhainebula/search-swe-base:cpu-py3.12-1.0.0
RUN useradd --create-home --uid 10001 --user-group submission
COPY . /tests/
COPY reference /task/tools/
RUN g++ -O3 -mavx2 -mfma -fopenmp -shared -fPIC /task/tools/maxsim.cpp -o /task/tools/libmaxsim.so \
    && g++ -O3 -mavx2 -mfma -fopenmp -shared -fPIC /task/tools/baseline/kernel.cpp /task/tools/baseline/collect.cpp -o /task/tools/baseline/libcandidate.so \
    && chmod -R a+rX /task/tools
RUN chmod 700 /tests /tests/test.sh
