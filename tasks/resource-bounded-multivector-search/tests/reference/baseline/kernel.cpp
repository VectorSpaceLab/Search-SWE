#include <algorithm>
#include <cstdint>
#include <limits>
#include <immintrin.h>

extern "C" void score_candidates(const float* vectors, const int64_t* offsets,
                                 const int32_t* documents, int64_t count,
                                 const float* query, float* scores, int threads) {
    alignas(32) float transposed_query[128 * 32];
    for (int dimension = 0; dimension < 128; ++dimension)
        for (int query_token = 0; query_token < 32; ++query_token)
            transposed_query[dimension * 32 + query_token] = query[query_token * 128 + dimension];

    #pragma omp parallel for num_threads(threads) schedule(static)
    for (int64_t candidate = 0; candidate < count; ++candidate) {
        const int64_t document = documents[candidate];
        __m256 best[4];
        for (int block = 0; block < 4; ++block)
            best[block] = _mm256_set1_ps(-std::numeric_limits<float>::infinity());

        int64_t token = offsets[document];
        for (; token + 1 < offsets[document + 1]; token += 2) {
            __m256 first[4], second[4];
            for (int block = 0; block < 4; ++block) {
                first[block] = _mm256_setzero_ps();
                second[block] = _mm256_setzero_ps();
            }
            for (int dimension = 0; dimension < 128; ++dimension) {
                const __m256 first_value = _mm256_set1_ps(vectors[token * 128 + dimension]);
                const __m256 second_value = _mm256_set1_ps(vectors[(token + 1) * 128 + dimension]);
                for (int block = 0; block < 4; ++block) {
                    const __m256 query_values = _mm256_load_ps(transposed_query + dimension * 32 + block * 8);
                    first[block] = _mm256_fmadd_ps(first_value, query_values, first[block]);
                    second[block] = _mm256_fmadd_ps(second_value, query_values, second[block]);
                }
            }
            for (int block = 0; block < 4; ++block)
                best[block] = _mm256_max_ps(best[block], _mm256_max_ps(first[block], second[block]));
        }

        if (token < offsets[document + 1]) {
            __m256 current[4];
            for (int block = 0; block < 4; ++block)
                current[block] = _mm256_setzero_ps();
            for (int dimension = 0; dimension < 128; ++dimension) {
                const __m256 value = _mm256_set1_ps(vectors[token * 128 + dimension]);
                for (int block = 0; block < 4; ++block) {
                    const __m256 query_values = _mm256_load_ps(transposed_query + dimension * 32 + block * 8);
                    current[block] = _mm256_fmadd_ps(value, query_values, current[block]);
                }
            }
            for (int block = 0; block < 4; ++block)
                best[block] = _mm256_max_ps(best[block], current[block]);
        }

        alignas(32) float maxima[32];
        for (int block = 0; block < 4; ++block)
            _mm256_store_ps(maxima + block * 8, best[block]);
        float total = 0.0f;
        for (int query_token = 0; query_token < 32; ++query_token)
            total += maxima[query_token];
        scores[candidate] = total;
    }
}
