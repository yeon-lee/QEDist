#pragma once
#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

// The optional budget accounts for live native vector capacity before allocation.
struct AllocationBudget {
    inline static size_t limit = 0;
    inline static size_t used = 0;
    inline static size_t peak = 0;
};

template<class T> struct BudgetAllocator {
    using value_type = T;
    using is_always_equal = std::true_type;
    BudgetAllocator() noexcept = default;
    template<class U> BudgetAllocator(const BudgetAllocator<U>&) noexcept {}
    T* allocate(size_t count) {
        if (count > std::numeric_limits<size_t>::max() / sizeof(T)) throw std::bad_alloc();
        size_t bytes = count * sizeof(T);
        if (bytes > std::numeric_limits<size_t>::max() - AllocationBudget::used ||
            (AllocationBudget::limit && bytes > AllocationBudget::limit - AllocationBudget::used))
            throw std::bad_alloc();
        T* result = std::allocator<T>{}.allocate(count);
        AllocationBudget::used += bytes;
        AllocationBudget::peak = std::max(AllocationBudget::peak, AllocationBudget::used);
        return result;
    }
    void deallocate(T* pointer, size_t count) noexcept {
        AllocationBudget::used -= count * sizeof(T);
        std::allocator<T>{}.deallocate(pointer, count);
    }
    template<class U> bool operator==(const BudgetAllocator<U>&) const noexcept { return true; }
    template<class U> bool operator!=(const BudgetAllocator<U>&) const noexcept { return false; }
};

template<class T> using Vector = std::vector<T, BudgetAllocator<T>>;
using Word = Vector<uint64_t>;
inline int bit(const Word &v, int j) { return (v[j / 64] >> (j % 64)) & 1; }
inline void toggle(Word &v, int j) { v[j / 64] ^= uint64_t(1) << (j % 64); }
inline int weight(const Word &v, int words) {
    int result = 0;
    for (int j = 0; j < words; ++j) result += __builtin_popcountll(v[j]);
    return result;
}
inline void xorin(Word &a, const Word &b, int words) {
    for (int j = 0; j < words; ++j) a[j] ^= b[j];
}
inline double elapsed(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}
inline volatile std::sig_atomic_t stopped = 0;
inline void stop_handler(int) { stopped = 1; }
inline void report_allocation_failure() {
    std::cout << "{\"event\":\"resource_limit\",\"resource\":\"memory\",\"limit_bytes\":"
              << AllocationBudget::limit << ",\"peak_bytes\":" << AllocationBudget::peak << "}\n";
}
inline void set_memory_budget(const std::string &value) {
    if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("invalid memory budget");
    auto bytes = std::stoull(value);
    if (!bytes || bytes > std::numeric_limits<size_t>::max())
        throw std::runtime_error("invalid memory budget");
    AllocationBudget::limit = size_t(bytes);
}

struct Basis {
    int n, words;
    Vector<Word> rows;
    Vector<int> pivots;
    explicit Basis(int n) : n(n), words((size_t(n) + 63) / 64) {}
    Word reduce(Word a) const {
        for (size_t i = 0; i < rows.size(); ++i)
            if (bit(a, pivots[i])) xorin(a, rows[i], words);
        return a;
    }
    bool nontrivial(Word a) const { return weight(reduce(std::move(a)), words) != 0; }
    void add(Word a) {
        a = reduce(std::move(a));
        for (int j = 0; j < n; ++j) if (bit(a, j)) {
            rows.push_back(std::move(a));
            pivots.push_back(j);
            break;
        }
    }
};

inline Word readword(std::istream &input, int n) {
    Word result((size_t(n) + 63) / 64);
    int length, site;
    if (!(input >> length) || length < 0 || length > n) throw std::runtime_error("invalid row length");
    while (length--) {
        if (!(input >> site) || site < 0 || site >= n || bit(result, site))
            throw std::runtime_error("invalid/duplicate coordinate");
        toggle(result, site);
    }
    return result;
}

struct BinaryCode {
    int n = 0, m = 0, g = 0, words = 0;
    Vector<Word> H, G;
    Vector<Vector<int>> hr, vc, gr, vg;
    Basis basis{0};
    explicit BinaryCode(const std::string &path) {
        std::ifstream input(path);
        if (!(input >> n >> m >> g) || n <= 0 || m < 0 || g < 0)
            throw std::runtime_error("invalid matrix header");
        words = (size_t(n) + 63) / 64;
        basis = Basis(n);
        hr.resize(m); vc.resize(n); gr.resize(g); vg.resize(n);
        for (int row = 0; row < m; ++row) {
            H.push_back(readword(input, n));
            for (int site = 0; site < n; ++site) if (bit(H.back(), site)) {
                hr[row].push_back(site); vc[site].push_back(row);
            }
        }
        for (int row = 0; row < g; ++row) {
            G.push_back(readword(input, n));
            basis.add(G.back());
            for (int site = 0; site < n; ++site) if (bit(G.back(), site)) {
                gr[row].push_back(site); vg[site].push_back(row);
            }
        }
        std::string extra;
        if (input >> extra) throw std::runtime_error("trailing matrix data");
        for (const auto &a : H) for (const auto &b : G) {
            int parity = 0;
            for (int word = 0; word < words; ++word) parity ^= __builtin_parityll(a[word] & b[word]);
            if (parity) throw std::runtime_error("checks/stabilizers do not commute");
        }
    }
    bool kernel(const Word &v) const {
        for (const auto &h : H) {
            int parity = 0;
            for (int j = 0; j < words; ++j) parity ^= __builtin_parityll(h[j] & v[j]);
            if (parity) return false;
        }
        return true;
    }
    void validate_translation(int period) const {
        if (period < 1 || n % period) throw std::runtime_error("invalid cyclic period");
        if (period == 1) return;
        Basis checks(n);
        for (const auto &row : H) checks.add(row);
        auto shifted = [&](const Word &v) {
            Word result(words);
            for (int j = 0; j < n; ++j)
                if (bit(v, j)) toggle(result, (j / period) * period + (j % period + 1) % period);
            return result;
        };
        for (const auto &row : H)
            if (checks.nontrivial(shifted(row))) throw std::runtime_error("check space is not translation invariant");
        for (const auto &row : G)
            if (basis.nontrivial(shifted(row))) throw std::runtime_error("stabilizer space is not translation invariant");
    }
};

// Sparse checks occupy one word. Larger rows use consecutive words and the
// iterator visits their available coordinates in the same increasing order.
struct AvailableSites {
    const Vector<int> &columns;
    const uint64_t *masks;
    size_t words;
    struct Iterator {
        const int *columns;
        const uint64_t *next_mask, *last_mask;
        uint64_t bits;
        void advance_word() {
            while (!bits && next_mask != last_mask) {
                bits = *next_mask++;
                columns += 64;
            }
        }
        int operator*() const { return columns[__builtin_ctzll(bits)]; }
        Iterator& operator++() { bits &= bits - 1; advance_word(); return *this; }
        bool operator!=(std::nullptr_t) const { return bits != 0; }
    };
    Iterator begin() const {
        Iterator result{columns.data(), words ? masks + 1 : masks,
                        words ? masks + words : masks, words ? masks[0] : 0};
        result.advance_word();
        return result;
    }
    std::nullptr_t end() const { return nullptr; }
};

inline void print_support(const Word &v, int n) {
    std::cout << '[';
    bool first = true;
    for (int j = 0; j < n; ++j) if (bit(v, j)) {
        if (!first) std::cout << ',';
        std::cout << j;
        first = false;
    }
    std::cout << ']';
}
