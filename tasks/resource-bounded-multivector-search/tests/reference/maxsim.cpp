// Blockwise exact MaxSim reduction. Dot products are supplied by FP32 BLAS.
#include <algorithm>
#include <cstdint>
#include <limits>
#include <immintrin.h>
extern "C" void reduce_maxsim(const float* dots, const int64_t* offsets,
                             int64_t docs, int64_t base, int nq,
                             float* scores, int threads) {
    #pragma omp parallel for num_threads(threads) schedule(static)
    for (int64_t d = 0; d < docs; ++d) {
        float maxima[512];
        std::fill(maxima, maxima + nq, -std::numeric_limits<float>::infinity());
        for (int64_t t = offsets[d] - base; t < offsets[d+1] - base; ++t) {
            const float* row = dots + t * nq;
            #pragma omp simd
            for (int i = 0; i < nq; ++i) maxima[i] = std::max(maxima[i], row[i]);
        }
        float total = 0;
        for (int i = 0; i < nq; ++i) total += maxima[i];
        scores[d] = total;
    }
}

// Fused FP32 exhaustive kernel for the fixed 32 x 128 ColBERT query shape.
// Across-token maxima stay in registers; no corpus-by-query score matrix.
extern "C" void exact_maxsim(const float* vectors, const int64_t* offsets,
                            int64_t docs, const float* query, float* scores,
                            int threads) {
    alignas(32) float qt[128 * 32];
    for (int d = 0; d < 128; ++d)
        for (int q = 0; q < 32; ++q) qt[d*32+q] = query[q*128+d];
    #pragma omp parallel for num_threads(threads) schedule(static)
    for (int64_t doc = 0; doc < docs; ++doc) {
        __m256 best[4];
        for (int b = 0; b < 4; ++b) best[b] = _mm256_set1_ps(-std::numeric_limits<float>::infinity());
        int64_t t = offsets[doc];
        for (; t + 1 < offsets[doc+1]; t += 2) {
            __m256 a[4], b[4];
            for (int j=0; j<4; ++j) a[j] = b[j] = _mm256_setzero_ps();
            for (int d=0; d<128; ++d) {
                __m256 x = _mm256_set1_ps(vectors[t*128+d]);
                __m256 y = _mm256_set1_ps(vectors[(t+1)*128+d]);
                for (int j=0; j<4; ++j) {
                    __m256 q = _mm256_load_ps(qt+d*32+j*8);
                    a[j] = _mm256_fmadd_ps(x, q, a[j]);
                    b[j] = _mm256_fmadd_ps(y, q, b[j]);
                }
            }
            for (int j=0; j<4; ++j) best[j] = _mm256_max_ps(best[j], _mm256_max_ps(a[j],b[j]));
        }
        if (t < offsets[doc+1]) {
            __m256 a[4];
            for (int j=0; j<4; ++j) a[j] = _mm256_setzero_ps();
            for (int d=0; d<128; ++d) {
                __m256 x = _mm256_set1_ps(vectors[t*128+d]);
                for (int j=0; j<4; ++j)
                    a[j] = _mm256_fmadd_ps(x, _mm256_load_ps(qt+d*32+j*8), a[j]);
            }
            for (int j=0; j<4; ++j) best[j] = _mm256_max_ps(best[j],a[j]);
        }
        alignas(32) float maxima[32];
        for (int j=0; j<4; ++j) _mm256_store_ps(maxima+j*8, best[j]);
        float total = 0;
        for (int q=0; q<32; ++q) total += maxima[q];
        scores[doc] = total;
    }
}
