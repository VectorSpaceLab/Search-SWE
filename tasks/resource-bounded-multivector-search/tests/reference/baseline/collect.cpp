#include <cstdint>
#include <algorithm>

extern "C" int64_t collect_candidates(const int32_t* token_documents,
                                       const int64_t* tokens,
                                       int64_t token_count,
                                       int64_t document_count,
                                       uint64_t* seen,
                                       int64_t word_count,
                                       int32_t* candidates) {
    std::fill(seen, seen + word_count, uint64_t{0});
    for (int64_t i = 0; i < token_count; ++i) {
        const int64_t token = tokens[i];
        if (token < 0) continue;
        const int32_t document = token_documents[token];
        if (document < 0 || document >= document_count) continue;
        seen[document >> 6] |= uint64_t{1} << (document & 63);
    }
    int64_t count = 0;
    for (int64_t word = 0; word < word_count; ++word) {
        uint64_t value = seen[word];
        while (value != 0) {
            const int bit = __builtin_ctzll(value);
            const int64_t document = (word << 6) + bit;
            if (document < document_count) candidates[count++] = static_cast<int32_t>(document);
            value &= value - 1;
        }
    }
    return count;
}
