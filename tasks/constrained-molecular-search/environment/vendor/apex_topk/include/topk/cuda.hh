/* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * apex_topk: Accelerated top-k operators for APEX.
 *
 * CUDA top-k operator implementation.
 * Written by Darren Hsu <dahsu@nvidia.com>, Elias Stehle <estehle@nvidia.com>
 */

#include <torch/extension.h>
#include <cstdint>  // For int32_t
#include <cub/cub.cuh>
#include <cub/device/device_topk.cuh>
#include <cuda/std/detail/__config>
#include <cuda/__execution/determinism.h>
#include <cuda/__execution/output_ordering.h>
#include <cuda/__execution/require.h>
#include <cuda/std/functional>

#include <thrust/device_vector.h>
#include <thrust/host_vector.h>
#include <thrust/iterator/zip_iterator.h>
#include <thrust/memory.h>
#include <thrust/sort.h>

namespace cub::detail
{
template <typename T1, typename T2>
struct Traits<cuda::std::tuple<T1, T2>>
{
  // The type used for the unsigned bit-representation
  using UnsignedBits = ::cuda::std::uint64_t;

  using t1_traits        = Traits<T1>;
  using t2_traits        = Traits<T2>;
  using t1_unsigned_bits = typename Traits<T1>::UnsignedBits;
  using t2_unsigned_bits = typename Traits<T2>::UnsignedBits;

  static constexpr int key1_bit_size = sizeof(t1_unsigned_bits) * 8;
  static constexpr int key2_bit_size = sizeof(t2_unsigned_bits) * 8;

  static constexpr UnsignedBits bit_mask_key1 = static_cast<UnsignedBits>(t1_unsigned_bits(-1));
  static constexpr UnsignedBits bit_mask_key2 = static_cast<UnsignedBits>(t2_unsigned_bits(-1));

  static __host__ __device__ __forceinline__ UnsignedBits TwiddleIn(UnsignedBits key)
  {
    // Note, tuple representation has the primary key in the least significant bits followed by the next most
    // significant key etc. Hence, we need to reverse the order of the keys in the unsigned representation
    auto unsigned_key1 = static_cast<t1_unsigned_bits>(key & bit_mask_key1);
    auto unsigned_key2 = static_cast<t2_unsigned_bits>((key >> key1_bit_size) & bit_mask_key2);
    unsigned_key1      = t1_traits::TwiddleIn(unsigned_key1);
    unsigned_key2      = t2_traits::TwiddleIn(unsigned_key2);
    return (static_cast<UnsignedBits>(unsigned_key1) << key2_bit_size | static_cast<UnsignedBits>(unsigned_key2));
  };

  static __host__ __device__ __forceinline__ UnsignedBits TwiddleOut(UnsignedBits key)
  {
    auto unsigned_key1 = static_cast<t1_unsigned_bits>(key >> key2_bit_size & bit_mask_key1);
    auto unsigned_key2 = static_cast<t2_unsigned_bits>(key & bit_mask_key2);
    unsigned_key1      = t1_traits::TwiddleOut(unsigned_key1);
    unsigned_key2      = t2_traits::TwiddleOut(unsigned_key2);
    return (static_cast<UnsignedBits>(unsigned_key2) << key1_bit_size | static_cast<UnsignedBits>(unsigned_key1));
  };

private:
  friend struct is_primitive_impl;

  static constexpr bool is_primitive = true;
};
}; // namespace cub::detail


namespace apex::cuda {

/* nested library tree data structure, from list[list[list[int]]] */
using LibraryTree = std::vector<std::vector<std::vector<int64_t>>>;

/* max_groups: maximum number of component r-groups per reaction.
 * max_terms: maximum second-dim size of the contributions tensor.
 */
static constexpr int max_groups = 4;
static constexpr int max_terms = 256;
static constexpr int blocks = 320;
static constexpr int threads_per_block_default = 1024;

/* struct holding each search result, identifies the molecule. */
using index_t = uint32_t;

/* simplest possible rectified linear unit. */
__host__ __device__ inline float relu(float x) {
    return x > 0.0f ? x : 0.0f;
}


std::tuple<std::vector<std::pair<int32_t, int32_t>>, std::vector<std::pair<int32_t, int32_t>>, std::vector<int64_t>> calculate_chunks(
    const torch::Tensor& libtree_size, const int64_t chunk_size) {
    const int32_t n_rxn = libtree_size.size(0);
    // We are doing bounds by reaction and the first synthon, so as to finely chunk the library
    // In this setting the rxn_bounds are inclusive, and the s1_bounds are exclusive
    std::vector<std::pair<int32_t, int32_t>> rxn_bounds;
    std::vector<std::pair<int32_t, int32_t>> s1_bounds;
    // Vector to store cumulative sum for each chunk
    std::vector<int64_t> chunk_cumsum; // first element is 0
    chunk_cumsum.push_back(0);
    int32_t rxn_start = 0;
    int32_t s1_start = 0;
    int32_t last_s1 = 0;
    int64_t running_sum = 0;
    int64_t chunk_running_sum = 0; // this will be the offset in other kernels
    int32_t i = 0; // Because we have have a while loop, we need to keep track of the index
    while (i < n_rxn) {
        int64_t s1_size = static_cast<int64_t>(libtree_size[i][0].item<int32_t>());
        int64_t cpd_per_s1 = static_cast<int64_t>(libtree_size[i][1].item<int32_t>());
        if (libtree_size[i][2].item<int32_t>() > 0) cpd_per_s1 *= static_cast<int64_t>(libtree_size[i][2].item<int32_t>());
        if (libtree_size[i][3].item<int32_t>() > 0) cpd_per_s1 *= static_cast<int64_t>(libtree_size[i][3].item<int32_t>());
        // If adding this reaction's compounds would exceed chunk size,
        // record the chunk and start a new one
        if (i == rxn_start) {
            if (running_sum + (s1_size - s1_start) * cpd_per_s1 <= chunk_size) {
                // First or the same reaction as the last chunk, and it's good to include the remainder of the reaction
                running_sum += (s1_size - s1_start) * cpd_per_s1;
                chunk_running_sum += (s1_size - s1_start) * cpd_per_s1;
                last_s1 = s1_size;
                i++;
            } else {
                // We need to split the reaction
                int64_t s1_to_take = (chunk_size - running_sum) / cpd_per_s1;
                if (s1_to_take == 0) {
                    throw std::runtime_error("A single s0 chunk is too large to fit in the chunk");
                } else {
                    // Take some s0 chunks of this single reaction
                    rxn_bounds.emplace_back(rxn_start, i);
                    s1_bounds.emplace_back(s1_start, s1_start + s1_to_take);
                    rxn_start = i;
                    s1_start = s1_start + s1_to_take;
                    chunk_running_sum += s1_to_take * cpd_per_s1;
                    chunk_cumsum.push_back(chunk_running_sum);
                    running_sum = 0;
                }
            }
        } else if (running_sum + s1_size * cpd_per_s1 <= chunk_size) { // Good to include the entire reaction
            running_sum += s1_size * cpd_per_s1;
            chunk_running_sum += s1_size * cpd_per_s1;
            last_s1 = s1_size;
            i++;
        } else {
            // We need to split the reaction
            int64_t s1_to_take = (chunk_size - running_sum) / cpd_per_s1;
            if (s1_to_take == 0) {
                // A signle s0 chunk is too large to fit in the chunk
                // So the chunk ends at the end of last reaction
                rxn_bounds.emplace_back(rxn_start, i-1);
                s1_bounds.emplace_back(s1_start, last_s1);
                rxn_start = i;
                s1_start = 0;
                chunk_cumsum.push_back(chunk_running_sum);
                running_sum = 0;
            } else { // Take some s0 chunks
                running_sum += s1_to_take * cpd_per_s1;
                chunk_running_sum += s1_to_take * cpd_per_s1;
                rxn_bounds.emplace_back(rxn_start, i);
                s1_bounds.emplace_back(s1_start, s1_to_take);
                rxn_start = i;
                s1_start = s1_to_take;
                chunk_cumsum.push_back(chunk_running_sum);
                running_sum = 0;
            }
        }
    }

    // Add final chunk if there are remaining reactions
    if (rxn_start < n_rxn) {
        rxn_bounds.emplace_back(rxn_start, n_rxn - 1);
        s1_bounds.emplace_back(s1_start, last_s1);
        // no need for the final element in chunk_cumsum
    }

    return std::make_tuple(rxn_bounds, s1_bounds, chunk_cumsum);
}

__global__ void initialize_score(float *score, float *slack, unsigned int topk, unsigned int chunk_size, int32_t rxn_start, int32_t s1_start) {
    for (unsigned int i = blockIdx.x * blockDim.x + threadIdx.x; i < topk + chunk_size; i += blockDim.x * gridDim.x) {
        if (rxn_start == 0 && s1_start == 0) {
            score[i] = -999999.0f;
            slack[i] = -999999.0f;
        }
        else if (i >= topk) { // from the second round on (when rxn_start > 0 and s1_start > 0), only empty the elements after topk
            score[i] = -999999.0f;
            slack[i] = -999999.0f;
        }
    }
}

__global__ void calculate_scores(
    int *pLibTree,
    int libtree_offset_start,
    int *pLibTree_size,
    float *contribs,
    int n_synthon,
    int n_terms,
    int *quadratic_ids,
    int *objective_ids,
    int n_obj,
    int *constraint_ids,
    float *constraint_bounds,
    int n_const,
    float *score,
    float *slack,
    int n_comp,
    unsigned int topk,
    int rxn_start,
    int rxn_end,
    int s1_start,
    int s1_end
) {
    // we do a simple loop over N_RXN, block over first n_synthon, and thread over second n_synthon
    // TODO: change memory mapping to [n_terms * n_synthon] for contribs and shared memory
    // So that memory read is coalesced (check tutorial)

    // Declare dynamic shared memory
    extern __shared__ float shared_memory[];
    __syncthreads();

    // Calculate offsets for each array in shared memory
    float* accums = shared_memory;
    float* caccums = &accums[n_terms*blockDim.x];
    int* shared_quadratic_ids_one_hot = (int*)&caccums[n_terms*blockDim.x];  // This is done as one hot, so it has a length of n_terms
    int* shared_objective_ids = (int*)&shared_quadratic_ids_one_hot[n_terms];
    int* shared_constraint_ids = (int*)&shared_objective_ids[n_obj];
    float* shared_constraint_bounds = (float*)&shared_constraint_ids[n_const*2];
    int* shared_constraint_ids_one_hot = (int*)&shared_constraint_bounds[n_const*2]; // This is created at runtime

    // populate shared_memory with contribs, quadratic_ids, objective_ids, and constraint_ids
    // note that accums is in the shape of n_terms * blockDim.x
    if (threadIdx.x == 0) {
        for (int i = 0; i < n_terms; i++) {
            shared_quadratic_ids_one_hot[i] = quadratic_ids[i];
        }
        for (int i = 0; i < n_obj; i++) {
            shared_objective_ids[i] = objective_ids[i];
        }
        // print shared_objective_ids[0] and objective_ids[0] only for block 0

        if (n_const > 0) {
            for (int i = 0; i < n_const*2; i++) {
                shared_constraint_ids[i] = constraint_ids[i];
            }
            for (int i = 0; i < n_const*2; i++) {
                shared_constraint_bounds[i] = constraint_bounds[i];
            }
            for (int i = 0; i < n_terms; i++) {
                shared_constraint_ids_one_hot[i] = 0;
            }
            for (int i = 0; i < n_const; i++) {
                shared_constraint_ids_one_hot[constraint_ids[i]] = 1;
            }
        }
    }

    __syncthreads();

    unsigned int ncpd_offset = 0;
    int32_t libtree_offset = libtree_offset_start;
    int rxn_idx = rxn_start;
    int j = 0; // The s1 that's being processed
    int jn = blockIdx.x; // job number
    while (rxn_idx <= rxn_end) {
        // Determine the job number and see if it's for the current block (blockIdx.x)
        int s1 = pLibTree_size[rxn_idx*n_comp];
        if (jn >= s1) {
            // This block doesn't have work for this rxn, but calculate the offset
            unsigned int n_cpd_this_rxn = 1;
            for (int k = 0; k < n_comp; k++) {
                if (pLibTree_size[rxn_idx*n_comp+k] > 0) {
                    if (rxn_idx == rxn_start && k == 0) {
                        n_cpd_this_rxn *= (pLibTree_size[rxn_idx*n_comp+k] - s1_start);
                    }
                    else {
                        n_cpd_this_rxn *= pLibTree_size[rxn_idx*n_comp+k];
                    }
                    libtree_offset += pLibTree_size[rxn_idx*n_comp+k];
                }
            }
            ncpd_offset += n_cpd_this_rxn;
            jn -= s1;
            rxn_idx++;
            continue;
        } else {
            // This block has work for this rxn
            j = jn;
            jn += gridDim.x;
        }

        if (rxn_idx == rxn_start && j < s1_start) continue;
        if (rxn_idx == rxn_end && j >= s1_end) continue;

        // TODO: Merge the rxn loop and the synthon 1 loop so that we always saturate blockDim.x
        // At least more than what a device has (160 for L40S, 72 for A10)
        int s2, s3, s4, synthon_idx;
        // load the remaining 3 pLibTree_size[rxn_idx] into registers
        s2 = pLibTree_size[rxn_idx*n_comp+1];
        s3 = pLibTree_size[rxn_idx*n_comp+2];
        s4 = pLibTree_size[rxn_idx*n_comp+3];
        // if (blockIdx.x == 0 && threadIdx.x == 0) {
        //     printf("s1: %d, s2: %d, s3: %d, s4: %d\n", s1, s2, s3, s4);
        // }
        // Explicitly deal with the 4 components in loops as that's what's known scientifically

        int j2 = rxn_idx == rxn_start ? j - s1_start : j; // To adjust for the s1_start, out of bound issues
        unsigned int i1 = static_cast<unsigned int>(j2); // This is for the score matrix index
        synthon_idx = pLibTree[libtree_offset + j];
        // if (blockIdx.x == 0 && threadIdx.x == 0) {
        //     printf("synthon_idx: %d\n", synthon_idx);
        // }
        // TODO: factor this out into a function __accum or something
        for (int term_idx = 0; term_idx < n_terms; term_idx++) {
            // put in the contrib for the first synthon, into the shared memory
            accums[term_idx*blockDim.x+threadIdx.x] = contribs[synthon_idx + term_idx*n_synthon];
        }

        for (int k = threadIdx.x; k < s2; k += blockDim.x) { // Second synthon list is always populated
            unsigned int i2 = i1 * s2 + k;
            synthon_idx = pLibTree[libtree_offset + s1 + k];

            for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                // put in the contrib for the first synthon, into the shared memory
                accums[term_idx*blockDim.x+threadIdx.x] += contribs[synthon_idx + term_idx*n_synthon];
            }

            if (s3 > 0) { // If there's a third synthon list
                if (s4 > 0) { // If there's a fourth synthon list
                    for (int l = 0; l < s3; l ++) {
                        unsigned int i3 = i2 * s3 + l;
                        synthon_idx = pLibTree[libtree_offset + s2 + s1 + l];

                        for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                            // put in the contrib for the first synthon, into the shared memory
                            accums[term_idx*blockDim.x+threadIdx.x] += contribs[synthon_idx + term_idx*n_synthon];
                        }

                        for (int m = 0; m < s4; m++) {
                            unsigned int i4 = i3 * s4 + m;
                            synthon_idx = pLibTree[libtree_offset + s3 + s2 + s1 + m];

                            for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                                // put in the contrib for the fourth synthon, into the shared memory
                                accums[term_idx*blockDim.x+threadIdx.x] += contribs[synthon_idx + term_idx*n_synthon];
                            }

                            // 4 synthon list
                            // finally, process the accum based on quadratic_ids, objective_ids,
                            // constraint_ids, and constraint_bounds
                            float local_score = 0.0f;
                            for (int obj_idx = 0; obj_idx < n_obj; obj_idx++) { // process the objective contribution
                                float val = accums[threadIdx.x + shared_objective_ids[obj_idx]*blockDim.x];
                                local_score += shared_quadratic_ids_one_hot[obj_idx] == 1 ? val * val : val;
                            }
                            // printf("blockIdx.x: %d, threadIdx.x: %d, local_score: %f, i3: %d\n", blockIdx.x, threadIdx.x, local_score, i3);
                            score[topk + ncpd_offset + i4] = local_score;

                            float local_slack = 0.0f;
                            if (n_const > 0) {
                                for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                                    // flush caccums to zero
                                    caccums[term_idx*blockDim.x+threadIdx.x] = 0.0f;
                                }
                                for (int const_idx = 0; const_idx < n_const; const_idx++) { // process the constraint contribution
                                    float val = accums[threadIdx.x + shared_constraint_ids[n_const+const_idx]*blockDim.x];
                                    float term = shared_quadratic_ids_one_hot[shared_constraint_ids[n_const+const_idx]] == 1 ? val * val : val;
                                    caccums[threadIdx.x + shared_constraint_ids[const_idx]*blockDim.x] += term;
                                }

                                for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                                    if (shared_constraint_ids_one_hot[term_idx] == 1) {
                                        // lower bound, then upper bound
                                        float val = caccums[term_idx*blockDim.x+threadIdx.x];
                                        local_slack -= relu(shared_constraint_bounds[term_idx] - val) +
                                            relu(val - shared_constraint_bounds[term_idx+n_const]);
                                    }
                                }
                            }
                            slack[topk + ncpd_offset + i4] = local_slack;

                            // subtract out accums
                            for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                                // subtract out the contrib for the fourth synthon, from the shared memory
                                accums[term_idx*blockDim.x+threadIdx.x] -= contribs[synthon_idx + term_idx*n_synthon];
                            }
                        }
                        // subtract out accums
                        synthon_idx = pLibTree[libtree_offset + s2 + s1 + l]; // go back to the third synthon
                        for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                            // subtract out the contrib for the third synthon, from the shared memory
                            accums[term_idx*blockDim.x+threadIdx.x] -= contribs[synthon_idx + term_idx*n_synthon];
                        }
                    }
                } else { // 3 synthon list
                    for (int l = 0; l < s3; l ++) {
                        int i3 = i2 * s3 + l;
                        synthon_idx = pLibTree[libtree_offset + s2 + s1 + l];

                        for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                            // put in the contrib for the third synthon, into the shared memory
                            accums[term_idx*blockDim.x+threadIdx.x] += contribs[synthon_idx + term_idx*n_synthon];
                        }

                    // 3 synthon list
                    // finally, process the accum based on quadratic_ids, objective_ids,
                    // constraint_ids, and constraint_bounds
                        float local_score = 0.0f;
                        for (int obj_idx = 0; obj_idx < n_obj; obj_idx++) { // process the objective contribution
                            float val = accums[threadIdx.x + shared_objective_ids[obj_idx]*blockDim.x];
                            local_score += shared_quadratic_ids_one_hot[obj_idx] == 1 ? val * val : val;
                        }
                        // printf("blockIdx.x: %d, threadIdx.x: %d, local_score: %f, i3: %d\n", blockIdx.x, threadIdx.x, local_score, i3);
                        score[topk + ncpd_offset + i3] = local_score;

                        float local_slack = 0.0f;
                        if (n_const > 0) {
                            for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                                // flush caccums to zero
                                caccums[term_idx*blockDim.x+threadIdx.x] = 0.0f;
                            }
                            for (int const_idx = 0; const_idx < n_const; const_idx++) { // process the constraint contribution
                                float val = accums[threadIdx.x + shared_constraint_ids[n_const+const_idx]*blockDim.x];
                                float term = shared_quadratic_ids_one_hot[shared_constraint_ids[n_const+const_idx]] == 1 ? val * val : val;
                                caccums[threadIdx.x + shared_constraint_ids[const_idx]*blockDim.x] += term;
                            }

                            for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                                if (shared_constraint_ids_one_hot[term_idx] == 1) {
                                    // lower bound, then upper bound
                                    float val = caccums[term_idx*blockDim.x+threadIdx.x];
                                    local_slack -= relu(shared_constraint_bounds[term_idx] - val) +
                                        relu(val - shared_constraint_bounds[term_idx+n_const]);
                                }
                            }
                        }
                        slack[topk + ncpd_offset + i3] = local_slack;

                        for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                            // subtract out the contrib for the third synthon, from the shared memory
                            accums[term_idx*blockDim.x+threadIdx.x] -= contribs[synthon_idx + term_idx*n_synthon];
                        }
                    }
                }
            } else { // 2 synthon list
            // finally, process the accum based on quadratic_ids, objective_ids,
            // finally, process the accum based on quadratic_ids, objective_ids,
            // constraint_ids, and constraint_bounds
                float local_score = 0.0f;
                for (int obj_idx = 0; obj_idx < n_obj; obj_idx++) { // process the objective contribution
                    float val = accums[threadIdx.x + shared_objective_ids[obj_idx]*blockDim.x];
                    local_score += shared_quadratic_ids_one_hot[obj_idx] == 1 ? val * val : val;
                }
                // printf("blockIdx.x: %d, threadIdx.x: %d, local_score: %f, i3: %d\n", blockIdx.x, threadIdx.x, local_score, i3);
                score[topk + ncpd_offset + i2] = local_score;

                float local_slack = 0.0f;
                if (n_const > 0) {
                    for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                        // flush caccums to zero
                        caccums[term_idx*blockDim.x+threadIdx.x] = 0.0f;
                    }
                    for (int const_idx = 0; const_idx < n_const; const_idx++) { // process the constraint contribution
                        float val = accums[threadIdx.x + shared_constraint_ids[n_const+const_idx]*blockDim.x];
                        float term = shared_quadratic_ids_one_hot[shared_constraint_ids[n_const+const_idx]] == 1 ? val * val : val;
                        caccums[threadIdx.x + shared_constraint_ids[const_idx]*blockDim.x] += term;
                    }

                    for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                        if (shared_constraint_ids_one_hot[term_idx] == 1) {
                            // lower bound, then upper bound
                            float val = caccums[term_idx*blockDim.x+threadIdx.x];
                            local_slack -= relu(shared_constraint_bounds[term_idx] - val) +
                                relu(val - shared_constraint_bounds[term_idx+n_const]);
                        }
                    }
                }
                slack[topk + ncpd_offset + i2] = local_slack;
            }

            synthon_idx = pLibTree[libtree_offset + s1 + k]; // go back to the second synthon
            for (int term_idx = 0; term_idx < n_terms; term_idx++) {
                // subtract out the contrib for the second synthon, from the shared memory
                accums[term_idx*blockDim.x+threadIdx.x] -= contribs[synthon_idx + term_idx*n_synthon];
            }
        } // synthon 2 loop
    } // while loop and synthon 1 loop
} // function

__global__ void process_insufficient_topk(
    float* scores,
    float* slack,
    unsigned long long *indices_kept,
    int64_t *n_cpd,
    unsigned int topk,
    unsigned long long offset,
    unsigned long long offsetp1
) {
    for (unsigned long long i = blockIdx.x * blockDim.x + threadIdx.x; i < offsetp1; i += blockDim.x * gridDim.x) {
        indices_kept[i] = i;
        // during first round, fill the indices_kept with the indices if there's insufficient topk
        // Doesn't need to be updated until accumulated number of compounds is greater than topk
    }
    for (unsigned long long i = blockIdx.x * blockDim.x + threadIdx.x; i < offsetp1 - offset; i += blockDim.x * gridDim.x) {
        scores[offset + i] = scores[topk + i]; // move the scores into the corresponding position
        slack[offset + i] = slack[topk + i]; // move the slack into the corresponding position
    }
}

// Note: these two kernels used to be one, but it introduced race conditions (indices_kept was updated in the second loop before being
// read as the buffer_indices, and it's extra bad in the case of unsorted indices)
// To achieve device-wide sync, I had to separate the two loops to two kernels
__global__ void maintain_topk_indices(
    float* scores,
    float* slack,
    float* out_scores,
    float* out_slack,
    unsigned int *indices,
    unsigned long long *indices_kept,
    unsigned long long *buffer_indices,
    unsigned int topk,
    unsigned long long offset
) {
    for (unsigned int i = blockIdx.x * blockDim.x + threadIdx.x; i < topk; i += blockDim.x * gridDim.x) {
        // If indices is less than topk, it's already in the topk from the last round, therefore its index is not changed
        // Else we need to add the offset to the index, and take the topk out
        /* Example: pick 2 out of 3, we'd have [top0, top1, sample0, sample1, sample2] with index [0, 1, 2, 3, 4] in the first round
            Offset is 0 in the first round.
            Let's say top 2 indices are 2 and 4 (can't be 0 and 1 because they are reserved for top k), we have [2, 4] in indices
            We then post-process the indices by subtracting topk, so we keep [0, 2] as the top 2 in indices_kept
            Next round, we'd have [sample0 (top0), sample2 (top1), sample3, sample4, sample5], with index [0, 1, 2, 3, 4]
            Offset is 3 in the second round.
            If top 2 are 0 and 4, we would then have [0, 4] in indices, and [0, 2] in indices_kept
            To get the final top 2, we look at the indices. If indices[i] < topk, this index is unchanged so we keep that in the indices_kept
            Otherwise it's a new index, so we subtract by topk and add the offset to the index (4 - 2 + 3 = 5)
            Therefore our indices_kept is [0, 5]
        */
        // Also update the scores for the next round
        // But don't update the indices_kept yet, because it's updated in the next kernel
        buffer_indices[i] = indices[i] < topk ? indices_kept[indices[i]] : static_cast<unsigned long long>(indices[i]) + offset - topk;
        scores[i] = out_scores[i];
        slack[i] = out_slack[i];
    }
}

__global__ void update_indices_kept(unsigned long long *indices_kept, unsigned long long *buffer_indices, unsigned int topk) {
    // separate loop to write to indices_kept
    for (unsigned int i = blockIdx.x * blockDim.x + threadIdx.x; i < topk; i += blockDim.x * gridDim.x) {
        indices_kept[i] = buffer_indices[i];
    }
}


__global__ void infer_reaction_and_synthon_indices(int64_t topk, int64_t *n_cpd,
    int32_t *libtree_offset_per_rxn, int32_t n_rxn, int32_t n_comp,
    unsigned long long *indices, int32_t *pLibTree,
    int32_t *pLibTree_size, int32_t *decoded_indices, int32_t *component_mapping_reverse) {
    // indices is actually just the indices_kept
    // need to copy over n_cpd to the GPU
    // need to allocate decoded_indices on the GPU (in the host func)
    // We already have pLibTree and pLibTree_size on the GPU
    int32_t rxn_idx = 0;
    int64_t remaining_index; // every thread has a value

    // allocate 2048 * 5 ints shared memory to store unsorted decoded_indices
    extern __shared__ int shared_int_memory[];
    __syncthreads();
    int* temp_decoded_indices = (int*)shared_int_memory;

    for (int64_t i = blockIdx.x * blockDim.x + threadIdx.x; i < topk; i += blockDim.x * gridDim.x) {

        // empty temp_decoded_indices
        for (int32_t j = 0; j < 5; j++) {
            temp_decoded_indices[threadIdx.x * 5 + j] = -1;
        }

        remaining_index = static_cast<int64_t>(indices[i]);

        for (int32_t j = 0; j < n_rxn; j++) {
            if (remaining_index < n_cpd[j]) { // found the reaction
                rxn_idx = j;
                break;  // Exit the loop once we find the reaction
            }
            remaining_index -= n_cpd[j];
        }
        temp_decoded_indices[threadIdx.x * 5] = rxn_idx;
        // now we need to find the synthon indices
        int32_t libtree_offset = libtree_offset_per_rxn[rxn_idx];
        int32_t s1 = pLibTree_size[rxn_idx*n_comp+0];
        int32_t s2 = pLibTree_size[rxn_idx*n_comp+1];
        int32_t s3 = pLibTree_size[rxn_idx*n_comp+2];
        int32_t s4 = pLibTree_size[rxn_idx*n_comp+3];
        if (s3 == 0) {
            // This reaction has only 2 components
            int32_t idx1 = remaining_index / s2;
            int32_t idx2 = remaining_index % s2 + s1;
            temp_decoded_indices[threadIdx.x * 5 + 1] = pLibTree[libtree_offset + idx1];
            temp_decoded_indices[threadIdx.x * 5 + 2] = pLibTree[libtree_offset + idx2];
        } else if (s4 == 0) {
            // This reaction has only 3 components
            int32_t idx1 = remaining_index / (s2 * s3);
            int32_t idx2 = (remaining_index % (s2 * s3)) / s3 + s1;
            int32_t idx3 = remaining_index % s3 + s1 + s2;
            temp_decoded_indices[threadIdx.x * 5 + 1] = pLibTree[libtree_offset + idx1];
            temp_decoded_indices[threadIdx.x * 5 + 2] = pLibTree[libtree_offset + idx2];
            temp_decoded_indices[threadIdx.x * 5 + 3] = pLibTree[libtree_offset + idx3];
        } else {
            // This reaction has 4 components
            int32_t idx1 = remaining_index / (s2 * s3 * s4);
            int32_t idx2 = (remaining_index % (s2 * s3 * s4)) / (s3 * s4) + s1;
            int32_t idx3 = (remaining_index % (s3 * s4)) / s4 + s1 + s2;
            int32_t idx4 = remaining_index % s4 + s1 + s2 + s3;
            temp_decoded_indices[threadIdx.x * 5 + 1] = pLibTree[libtree_offset + idx1];
            temp_decoded_indices[threadIdx.x * 5 + 2] = pLibTree[libtree_offset + idx2];
            temp_decoded_indices[threadIdx.x * 5 + 3] = pLibTree[libtree_offset + idx3];
            temp_decoded_indices[threadIdx.x * 5 + 4] = pLibTree[libtree_offset + idx4];
        }

        // now we need to reverse the component mapping
        decoded_indices[i * 5] = temp_decoded_indices[threadIdx.x * 5];
        for (int32_t j = 0; j < 4; j++) {
            // temp_decoded_indices[threadIdx.x * 5] gets the reaction index
            // temp_decoded_indices[threadIdx.x * 5 + j] gets the synthon index
            decoded_indices[i * 5 + j + 1] = temp_decoded_indices[threadIdx.x * 5 + component_mapping_reverse[temp_decoded_indices[threadIdx.x * 5] * 4 + j] + 1];
        }
    }
}

std::tuple<torch::Tensor, torch::Tensor>
topk(
    torch::Tensor contribs,
    torch::Tensor quadratic_ids,
    torch::Tensor objective_ids,
    torch::Tensor constraint_ids,
    torch::Tensor constraint_bounds,
    const LibraryTree& libtree_data,
    const int64_t topk,
    bool descending,
    // 2^30 = 1073741824, should adjust for GPU memory,
    // but can be in 64-bit territory
    const int64_t default_chunk_size = 1 << 30
) {
    // start timer for sanity check
    auto start_sanity_check = std::chrono::high_resolution_clock::now();

    /* check a few things for safety... */
    const int64_t max_contribs = std::numeric_limits<int64_t>::max();

    if (contribs.size(/*dim=*/0) >= max_contribs)
        throw std::length_error{"exceeded maximum number of contributions"};

    if (contribs.size(/*dim=*/1) >= max_terms)
        throw std::length_error{"exceeded maximum number of score terms"};

    if (quadratic_ids.lt(0).any().item<bool>() ||
        quadratic_ids.ge(max_terms).any().item<bool>())
        throw std::length_error{"quadratic indices are out of bounds"};

    if (constraint_ids.lt(0).any().item<bool>() ||
        constraint_ids.ge(max_terms).any().item<bool>())
        throw std::length_error{"constraint indices are out of bounds"};

    // end timer for sanity check
    auto end_sanity_check = std::chrono::high_resolution_clock::now();
    auto duration_sanity_check = std::chrono::duration_cast<std::chrono::milliseconds>(end_sanity_check - start_sanity_check);

    // start timer for gathering synthon information
    auto start_gather_synthon_info = std::chrono::high_resolution_clock::now();

    const auto n_rxn = libtree_data.size();
    const auto n_synthon = contribs.size(0);
    const int32_t n_terms = static_cast<int32_t>(contribs.size(1));
    const int32_t n_constraint = constraint_ids.numel() ? static_cast<int32_t>(constraint_ids.size(1)) : 0;
    const int32_t n_obj = objective_ids.numel() ? static_cast<int32_t>(objective_ids.size(0)) : 0;

    // Transform data
    // create a one hot vector for the quadratic_ids
    auto quadratic_ids_one_hot = torch::zeros({n_terms}, /*options=*/torch::kInt32);
    for (int32_t i = 0; i < quadratic_ids.size(0); i++) {
        quadratic_ids_one_hot[static_cast<int32_t>(quadratic_ids[i].item<int64_t>())] = 1;
    }

    // transform contribs to float
    auto contribs_float = contribs.to(torch::kFloat32);
    // transpose contribs from [n_synthon, n_terms] to [n_terms, n_synthon] for better memory access pattern
    auto contribs_float_t = contribs_float.t().contiguous();
    // transform objective_ids to int
    auto objective_ids_int = objective_ids.to(torch::kInt32);
    // transform constraint_ids to int
    auto constraint_ids_int = constraint_ids.to(torch::kInt32);
    // transform constraint_bounds to float
    auto constraint_bounds_float = constraint_bounds.to(torch::kFloat32);

    auto libtree_offset_per_rxn = torch::zeros({static_cast<int32_t>(n_rxn)}, /*options=*/torch::kInt32);
    int32_t total_synthons = 0;
    // initiate an array to hold the number of compounds for each reaction
    auto n_cpd = torch::ones({static_cast<int32_t>(n_rxn)}, /*options=*/torch::kInt64);
    for (int32_t i = 0; i < libtree_data.size(); ++i) {
        for (const auto& synth : libtree_data[i]) {
            total_synthons += static_cast<int32_t>(synth.size());
            n_cpd[i] *= static_cast<int64_t>(synth.size());
        }
        if (i < libtree_data.size() - 1) {
            libtree_offset_per_rxn[i + 1] = total_synthons;  // Basically a cumulative sum of the number of synthons
        }
    }

    // calculate sum of n_cpd
    int64_t sum_n_cpd = n_cpd.sum().item<int64_t>();

    if (sum_n_cpd < topk) {
        throw std::runtime_error("total number of compounds is less than topk. Your entire library is good.");
    }

    // end timer for gathering synthon information
    auto end_gather_synthon_info = std::chrono::high_resolution_clock::now();
    auto duration_gather_synthon_info = std::chrono::duration_cast<std::chrono::milliseconds>(end_gather_synthon_info - start_gather_synthon_info);

    // start timer for filling flat libtree_data and libtree_size
    auto start_fill_flat_libtree = std::chrono::high_resolution_clock::now();

    // Allocate memory for the flat libtree_data and libtree_size
    const auto i32 = torch::dtype(torch::kInt32);
    auto flat_libtree = torch::empty({static_cast<int32_t>(total_synthons)}, /*options=*/i32);
    int32_t flat_libtree_idx = 0;
    // Create tensor to hold sizes of each component
    auto libtree_size = torch::zeros({static_cast<int32_t>(libtree_data.size()), 4}, /*options=*/i32);

    // start timer for swapping components
    auto duration_swap_components_part = std::chrono::duration<double>::zero();
    auto duration_fill_flat_libtree_part = std::chrono::duration<double>::zero();

    // keep track of the component mapping (specifically the reverse mapping for later reconstruction)
    std::vector<int32_t> component_mapping_reverse(libtree_data.size() * 4 );

    for (int32_t i = 0; i < libtree_data.size(); ++i) {

        auto start_swap_components_loop = std::chrono::high_resolution_clock::now();

        // vector of size 4 to hold the sizes of the components
        std::vector<int32_t> component_sizes(4);
        std::vector<int32_t> component_mapping{0, 1, 2, 3};
        for (int32_t j = 0; j < libtree_data[i].size(); ++j) {
            // sort the component by size, we want [big, biggest, rest of them]
            component_sizes[j] = libtree_data[i][j].size();
            if (j == 1) {
                if (component_sizes[j] < component_sizes[0]) {
                    std::swap(component_sizes[j], component_sizes[0]);
                    std::swap(component_mapping[j], component_mapping[0]);
                }
            }
            else if (j >= 2) {
                if (component_sizes[j] > component_sizes[1]) {
                    std::swap(component_sizes[j], component_sizes[0]);
                    std::swap(component_sizes[1], component_sizes[0]);
                    std::swap(component_mapping[j], component_mapping[0]);
                    std::swap(component_mapping[1], component_mapping[0]);
                }
                else if (component_sizes[j] > component_sizes[0]) {
                    std::swap(component_sizes[j], component_sizes[0]);
                    std::swap(component_mapping[j], component_mapping[0]);
                }
            }
        }

        // keep track of the reverse mapping
        for (int32_t j = 0; j < 4; j++) {
            component_mapping_reverse[i * 4 + component_mapping[j]] = j;
        }

        auto end_swap_components_loop = std::chrono::high_resolution_clock::now();
        duration_swap_components_part += std::chrono::duration_cast<std::chrono::milliseconds>(end_swap_components_loop - start_swap_components_loop);

        auto start_fill_flat_libtree_loop = std::chrono::high_resolution_clock::now();
        for (int32_t j = 0; j < libtree_data[i].size(); ++j) {
            const auto& component = libtree_data[i][component_mapping[j]];
            const auto component_size = static_cast<int32_t>(component.size());
            libtree_size[i][j] = component_size;

            // Copy entire component at once instead of element by element
            std::copy(component.begin(), component.end(),
                     flat_libtree.data_ptr<int32_t>() + flat_libtree_idx);
            flat_libtree_idx += component_size;
        }
        auto end_fill_flat_libtree_loop = std::chrono::high_resolution_clock::now();
        duration_fill_flat_libtree_part += std::chrono::duration_cast<std::chrono::milliseconds>(end_fill_flat_libtree_loop - start_fill_flat_libtree_loop);
    }

    // end timer for filling flat libtree_data and libtree_size
    auto end_fill_flat_libtree = std::chrono::high_resolution_clock::now();
    auto duration_fill_flat_libtree = std::chrono::duration_cast<std::chrono::milliseconds>(end_fill_flat_libtree - start_fill_flat_libtree);



    // start timer for the preprocessing part
    auto start_chunk_calculation = std::chrono::high_resolution_clock::now();

    // Determine actual chunk size
    int64_t chunk_size;
    if (sum_n_cpd >= default_chunk_size) {
        // we'll use the s0 granularity for the chunk size
        chunk_size = default_chunk_size;
    }
    else {
        chunk_size = sum_n_cpd;
    }

    // 2. Determine the number of chunks needed to process the libtree_data
    // Calculate running sum of compounds and split into chunks
    // chunks is a vector of pairs of int32_t, the first element is the start index of the chunk, the second element is the end index of the chunk
    // offsets is a vector of int64_t, the first element is 0, and the rest are the cumulative sum of the number of compounds in the previous chunks
    auto [chunks, s1_bounds, offsets] = calculate_chunks(libtree_size, chunk_size);

    // Using chunk information, calculate libtree_offset_start for each chunk
    auto libtree_offset_start = torch::zeros({static_cast<int32_t>(chunks.size())}, /*options=*/i32);
    for (int i = 1; i < chunks.size(); i++) {
        libtree_offset_start[i] = libtree_offset_start[i-1];
        for (int j = chunks[i-1].first; j < chunks[i].first; j++) {
            libtree_offset_start[i] += libtree_size[j].sum().item<int32_t>();
        }
    }

    // print timing for the chunk calculation
    auto end_chunk_calculation = std::chrono::high_resolution_clock::now();
    auto duration_chunk_calculation = std::chrono::duration_cast<std::chrono::milliseconds>(end_chunk_calculation - start_chunk_calculation);

    // With the padded libtree_data and libtree_size, we can follow the implementation in outer_addition.cu
    // to calculate scores in the chunks.

    // start timer for GPU part
    auto start_allocate = std::chrono::high_resolution_clock::now();
    // Copy padded_libtree and libtree_size to GPU
    thrust::device_vector<int32_t> d_pLibTree(total_synthons);
    thrust::device_vector<int32_t> d_pLibTree_size(libtree_data.size() * 4);
    thrust::copy(flat_libtree.data_ptr<int32_t>(), flat_libtree.data_ptr<int32_t>() + total_synthons, d_pLibTree.begin());
    thrust::copy(libtree_size.data_ptr<int32_t>(), libtree_size.data_ptr<int32_t>() + libtree_data.size() * 4, d_pLibTree_size.begin());
    // copy contribs to GPU
    // note in this version we copy the transposed contribs for hopefully better memory coalescing
    thrust::device_vector<float> d_contribs(contribs.size(0) * n_terms);
    thrust::copy(contribs_float_t.data_ptr<float>(), contribs_float_t.data_ptr<float>() + contribs.size(0) * n_terms, d_contribs.begin());

    // copy quadratic_ids_one_hot to GPU
    thrust::device_vector<int> d_quadratic_ids_one_hot(n_terms);
    thrust::copy(quadratic_ids_one_hot.data_ptr<int>(), quadratic_ids_one_hot.data_ptr<int>() + n_terms, d_quadratic_ids_one_hot.begin());

    // copy objective_ids to GPU
    thrust::device_vector<int> d_objective_ids(n_obj);
    if (n_obj > 0) {
        thrust::copy(objective_ids_int.data_ptr<int>(), objective_ids_int.data_ptr<int>() + n_obj, d_objective_ids.begin());
    }

    // copy constraint_bounds to GPU
    thrust::device_vector<float> d_constraint_bounds(n_constraint * 2);
    thrust::device_vector<int> d_constraint_ids(n_constraint * 2);
    if (n_constraint > 0) {
        thrust::copy(constraint_bounds_float.data_ptr<float>(), constraint_bounds_float.data_ptr<float>() + n_constraint * 2, d_constraint_bounds.begin());
        thrust::copy(constraint_ids_int.data_ptr<int>(), constraint_ids_int.data_ptr<int>() + n_constraint * 2, d_constraint_ids.begin());
    }

    // Allocate GPU array to hold up to topk + chunk_size floats
    thrust::device_vector<float> d_scores(topk + chunk_size, -std::numeric_limits<float>::infinity());
    thrust::device_vector<float> d_slack(topk + chunk_size, -std::numeric_limits<float>::infinity());

    // Allocate GPU array to hold topk scores for output and next round
    thrust::device_vector<float> d_out_scores(topk);
    thrust::device_vector<float> d_out_slack(topk);

    // Allocate GPU array to hold topk indices
    thrust::device_vector<unsigned int> d_indices(topk);
    thrust::device_vector<unsigned long long> d_indices_kept(topk);
    thrust::device_vector<unsigned long long> d_buffer_indices(topk);

    // copy n_cpd to GPU
    thrust::device_vector<int64_t> d_n_cpd(n_cpd.size(0));
    thrust::copy(n_cpd.data_ptr<int64_t>(), n_cpd.data_ptr<int64_t>() + n_cpd.size(0), d_n_cpd.begin());

    // copy libtree_offset_start to GPU
    thrust::device_vector<int32_t> d_libtree_offset_per_rxn(libtree_offset_per_rxn.size(0));
    thrust::copy(libtree_offset_per_rxn.data_ptr<int32_t>(), libtree_offset_per_rxn.data_ptr<int32_t>() + libtree_offset_per_rxn.size(0), d_libtree_offset_per_rxn.begin());

    // copy component_mapping_reverse to GPU
    thrust::device_vector<int32_t> d_component_mapping_reverse(libtree_data.size() * 4);
    thrust::copy(component_mapping_reverse.begin(), component_mapping_reverse.end(), d_component_mapping_reverse.begin());

    // stop timer for GPU part
    auto end_allocate = std::chrono::high_resolution_clock::now();
    auto duration_allocate = std::chrono::duration_cast<std::chrono::milliseconds>(end_allocate - start_allocate);


    // Calculate total shared memory size needed
    int threads_per_block = (((48*1024 - 4 * (2*n_terms + objective_ids.size(0) + n_constraint * 4)) / 2 / 4 / n_terms)) / 32 * 32;
    if (threads_per_block > 1024) {
        threads_per_block = 1024;
    }

    size_t shared_memory_size =
        sizeof(float) * n_terms * threads_per_block +     // accums
        sizeof(float) * n_terms * threads_per_block +     // caccums
        sizeof(int) * n_terms +                   // shared_quadratic_ids_one_hot
        sizeof(int) * objective_ids.size(0) +                     // shared_objective_ids
        sizeof(int) * n_constraint * 2 +               // shared_constraint_ids
        sizeof(float) * n_constraint * 2 +             // shared_constraint_bounds
        sizeof(int) * n_terms;                    // shared_constraint_ids_one_hot

    // launch the kernel "calculate_scores"
    // loop through the pairs in chunks
    for (int i = 0; i < chunks.size(); i++) {

        // start timer for kernel launch
        auto start_initialize = std::chrono::high_resolution_clock::now();
        // Configure kernel launch parameters

        // Launch kernel to initialize scores for current chunk
        initialize_score<<<blocks, threads_per_block_default>>>(
            thrust::raw_pointer_cast(d_scores.data()),
            thrust::raw_pointer_cast(d_slack.data()),
            static_cast<unsigned int>(topk),
            static_cast<unsigned int>(chunk_size),
            chunks[i].first,
            s1_bounds[i].first
        );
        if (cudaGetLastError() != cudaSuccess) {
            throw std::runtime_error("Failed to launch initialize_score kernel");
        }
        if (cudaDeviceSynchronize() != cudaSuccess) {
            throw std::runtime_error("Failed to synchronize after initialize_score kernel");
        }
        auto end_initialize = std::chrono::high_resolution_clock::now();
        auto duration_initialize = std::chrono::duration_cast<std::chrono::milliseconds>(end_initialize - start_initialize);

        // Launch kernel to calculate scores for current chunk
        auto start_calculate = std::chrono::high_resolution_clock::now();

        calculate_scores<<<blocks, threads_per_block, shared_memory_size>>>(
            thrust::raw_pointer_cast(d_pLibTree.data()),
            libtree_offset_start[i].item<int32_t>(),
            thrust::raw_pointer_cast(d_pLibTree_size.data()),
            thrust::raw_pointer_cast(d_contribs.data()),
            n_synthon,
            n_terms, // which is contribs.size(1)
            thrust::raw_pointer_cast(d_quadratic_ids_one_hot.data()),
            thrust::raw_pointer_cast(d_objective_ids.data()),
            n_obj,
            thrust::raw_pointer_cast(d_constraint_ids.data()),
            thrust::raw_pointer_cast(d_constraint_bounds.data()),
            n_constraint,
            thrust::raw_pointer_cast(d_scores.data()),
            thrust::raw_pointer_cast(d_slack.data()),
            4,
            topk,
            chunks[i].first,
            chunks[i].second,
            s1_bounds[i].first,
            s1_bounds[i].second
        );
        if (cudaGetLastError() != cudaSuccess) {
            std::cout << "Error: " << cudaGetErrorString(cudaGetLastError()) << std::endl;
            throw std::runtime_error("Failed to launch calculate_scores kernel");
        }
        if (cudaDeviceSynchronize() != cudaSuccess) {
            std::cout << "Error: " << cudaGetErrorString(cudaGetLastError()) << std::endl;
            throw std::runtime_error("Failed to synchronize after calculate_scores kernel");
        }
        auto end_calculate = std::chrono::high_resolution_clock::now();
        auto duration_calculate = std::chrono::duration_cast<std::chrono::milliseconds>(end_calculate - start_calculate);

        if (i < chunks.size() - 1 && offsets[i+1] < topk) {
            // If accumulated_size is less than topk, then we don't need to do topk.
            // However, we do need to move the scores and indices around
            auto start_process = std::chrono::high_resolution_clock::now();
            process_insufficient_topk<<<blocks, threads_per_block_default>>>(
                thrust::raw_pointer_cast(d_scores.data()),
                thrust::raw_pointer_cast(d_slack.data()),
                thrust::raw_pointer_cast(d_indices_kept.data()),
                thrust::raw_pointer_cast(d_n_cpd.data()),
                static_cast<unsigned int>(topk),
                static_cast<unsigned long long>(offsets[i]),
                static_cast<unsigned long long>(offsets[i+1])
            );
            if (cudaGetLastError() != cudaSuccess) {
                throw std::runtime_error("Failed to launch process_insufficient_topk kernel");
            }
            if (cudaDeviceSynchronize() != cudaSuccess) {
                throw std::runtime_error("Failed to synchronize after process_insufficient_topk kernel");
            }
            auto end_process = std::chrono::high_resolution_clock::now();
            auto duration_process = std::chrono::duration_cast<std::chrono::milliseconds>(end_process - start_process);
            // start timer for kernel launch


        } else { // We do top k - include the whole rest of the block

            // By now we have prepared the d_score array for the current chunk, with possibly some scores as minus infinity
            // the sorting in the reference top k is selecting the highest scores first from slack, then objective
            // Slack is always negative, while objective is always positive


            // start timer for kernel launch
            auto start_topk = std::chrono::high_resolution_clock::now();

            // Slack is more important than objective, so we sort by slack first
            auto keys_in_zipped = thrust::make_zip_iterator(d_slack.cbegin(), d_scores.cbegin());
            auto keys_out_zipped = thrust::make_zip_iterator(d_out_slack.begin(), d_out_scores.begin());
            auto values_in = thrust::make_counting_iterator(index_t{});
            // Allocate temporary buffer for topk operation
            size_t temp_buffer_size = 0;

            // Specify that we do not require a specific output order and do not require deterministic results
            auto requirements =
                ::cuda::execution::require(::cuda::execution::determinism::not_guaranteed, ::cuda::execution::output_ordering::unsorted);

            // Query temporary storage requirements
            cub::DeviceTopK::MaxPairs(
                nullptr,
                temp_buffer_size,
                keys_in_zipped,
                keys_out_zipped,
                values_in,
                d_indices.begin(),
                static_cast<unsigned int>(chunk_size + topk),
                static_cast<unsigned int>(topk),
                requirements
            );

            if (cudaGetLastError() != cudaSuccess) {
                throw std::runtime_error("Failed to launch cub::DeviceTopK::TopKPairs kernel");
            }
            if (cudaDeviceSynchronize() != cudaSuccess) {
                throw std::runtime_error("Failed to synchronize after cub::DeviceTopK::TopKPairs kernel");
            }

            // Allocate temporary storage
            thrust::device_vector<char> d_temp_storage(temp_buffer_size);
            auto temp_storage_ptr = thrust::raw_pointer_cast(d_temp_storage.data());

            cub::DeviceTopK::MaxPairs(
                temp_storage_ptr,
                temp_buffer_size,
                keys_in_zipped,
                keys_out_zipped,
                values_in,
                d_indices.begin(),
                static_cast<unsigned int>(chunk_size + topk),
                static_cast<unsigned int>(topk),
                requirements
            );
            if (cudaGetLastError() != cudaSuccess) {
                throw std::runtime_error("Failed to launch second cub::DeviceTopK::TopKPairs kernel");
            }
            if (cudaDeviceSynchronize() != cudaSuccess) {
                throw std::runtime_error("Failed to synchronize after second cub::DeviceTopK::TopKPairs kernel");
            }

            auto end_topk = std::chrono::high_resolution_clock::now();
            auto duration_topk = std::chrono::duration_cast<std::chrono::milliseconds>(end_topk - start_topk);

            auto start_maintain = std::chrono::high_resolution_clock::now();
            maintain_topk_indices<<<blocks, threads_per_block_default>>>(
                thrust::raw_pointer_cast(d_scores.data()),
                thrust::raw_pointer_cast(d_slack.data()),
                thrust::raw_pointer_cast(d_out_scores.data()),
                thrust::raw_pointer_cast(d_out_slack.data()),
                thrust::raw_pointer_cast(d_indices.data()),
                thrust::raw_pointer_cast(d_indices_kept.data()),
                thrust::raw_pointer_cast(d_buffer_indices.data()),
                static_cast<unsigned int>(topk),
                static_cast<unsigned long long>(offsets[i])
            );
            if (cudaGetLastError() != cudaSuccess) {
                throw std::runtime_error("Failed to launch maintain_topk_indices kernel");
            }
            if (cudaDeviceSynchronize() != cudaSuccess) {
                throw std::runtime_error("Failed to synchronize after maintain_topk_indices kernel");
            }

            update_indices_kept<<<blocks, threads_per_block_default>>>(
                thrust::raw_pointer_cast(d_indices_kept.data()),
                thrust::raw_pointer_cast(d_buffer_indices.data()),
                static_cast<unsigned int>(topk)
            );
            if (cudaGetLastError() != cudaSuccess) {
                throw std::runtime_error("Failed to launch update_indices_kept kernel");
            }
            if (cudaDeviceSynchronize() != cudaSuccess) {
                throw std::runtime_error("Failed to synchronize after update_indices_kept kernel");
            }

            auto end_maintain = std::chrono::high_resolution_clock::now();
            auto duration_maintain = std::chrono::duration_cast<std::chrono::milliseconds>(end_maintain - start_maintain);
        }
    }

    // sort the output
    auto keys_out_zipper = thrust::make_zip_iterator(d_out_slack.begin(), d_out_scores.begin(), d_indices_kept.begin());
    thrust::sort(keys_out_zipper, keys_out_zipper + topk, thrust::greater<>{});

    // start timer for GPU part
    auto start_copy_back = std::chrono::high_resolution_clock::now();
    // Now we have the topk scores and indices in the first topk elements of the d_score and d_indices arrays
    // TODO: copy that part of the d_score and d_indices arrays to the CPU
    std::vector<float> scores(topk);
    std::vector<float> slack(topk);
    std::vector<unsigned long long> indices(topk);
    thrust::copy(d_out_scores.begin(), d_out_scores.end(), scores.begin());
    thrust::copy(d_out_slack.begin(), d_out_slack.end(), slack.begin());
    thrust::copy(d_indices_kept.begin(), d_indices_kept.end(), indices.begin());

    // stop timer for GPU part
    // print that we're done with the GPU part
    auto end_copy_back = std::chrono::high_resolution_clock::now();
    auto duration_copy_back = std::chrono::duration_cast<std::chrono::milliseconds>(end_copy_back - start_copy_back);

    // start timer for kernel launch
    auto start_infer = std::chrono::high_resolution_clock::now();

    // Allocate decoded indices tensor
    auto decoded_indices = torch::empty({topk, 5}, torch::dtype(torch::kInt32));
    thrust::device_vector<int32_t> d_decoded_indices(topk * 5, -1);

    infer_reaction_and_synthon_indices<<<blocks, threads_per_block_default, threads_per_block_default * 5 * sizeof(int32_t)>>>(
        topk,
        thrust::raw_pointer_cast(d_n_cpd.data()),
        thrust::raw_pointer_cast(d_libtree_offset_per_rxn.data()),
        static_cast<int32_t>(n_rxn),
        4,
        thrust::raw_pointer_cast(d_indices_kept.data()),
        thrust::raw_pointer_cast(d_pLibTree.data()),
        thrust::raw_pointer_cast(d_pLibTree_size.data()),
        thrust::raw_pointer_cast(d_decoded_indices.data()),
        thrust::raw_pointer_cast(d_component_mapping_reverse.data())
    );

    if (cudaGetLastError() != cudaSuccess) {
        // print error message
        std::cout << "Error: " << cudaGetErrorString(cudaGetLastError()) << std::endl;
        throw std::runtime_error("Failed to launch infer_reaction_and_synthon_indices kernel");
    }
    if (cudaDeviceSynchronize() != cudaSuccess) {
        // print error message
        std::cout << "Error: " << cudaGetErrorString(cudaGetLastError()) << std::endl;
        throw std::runtime_error("Failed to synchronize after infer_reaction_and_synthon_indices kernel");
    }

    // Copy decoded indices back to host
    thrust::copy(d_decoded_indices.begin(), d_decoded_indices.end(), decoded_indices.data_ptr<int32_t>());

    auto end_infer = std::chrono::high_resolution_clock::now();
    auto duration_infer = std::chrono::duration_cast<std::chrono::milliseconds>(end_infer - start_infer);

    // Create output tensors
    auto scores_tensor = torch::empty({topk, 2}, torch::dtype(torch::kFloat32));
    auto scores_accessor = scores_tensor.accessor<float, 2>();
    for (int32_t i = 0; i < topk; i++) {
        scores_accessor[i][0] = slack[i];
        scores_accessor[i][1] = scores[i];
    }

    if (!descending) {
      scores_tensor = scores_tensor.flipud();
      decoded_indices = decoded_indices.flipud();
    }

    return {scores_tensor, decoded_indices.to(torch::kInt64)};
}

} /* namespace apex::cuda */

