// Each generator preserves the syndrome kernel and the stabilizer row space.
// Joint orbits need no enumeration of the group, including for product groups.
#pragma once
#include <sstream>

struct SymmetryRoots {
    std::vector<int> representatives;
    int generator_count = 0;
    bool explicit_generators = false;

    SymmetryRoots(const BinaryCode &code, int period, const std::string &path, int anchor = 0) {
        std::vector<int> parent(code.n);
        for (int site = 0; site < code.n; ++site) parent[site] = (site / period) * period;
        auto find = [&](int site) {
            while (site != parent[site]) {
                parent[site] = parent[parent[site]];
                site = parent[site];
            }
            return site;
        };
        explicit_generators = !path.empty();
        if (explicit_generators) {
            std::ifstream input(path);
            int n;
            if (!(input >> n >> generator_count) || n != code.n || generator_count < 0)
                throw std::runtime_error("invalid symmetry header");
            Basis checks(code.n);
            for (const auto &row : code.H) checks.add(row);
            for (int index = 0; index < generator_count; ++index) {
                std::vector<int> permutation(code.n);
                std::vector<bool> seen(code.n, false);
                for (int site = 0; site < code.n; ++site) {
                    int &image = permutation[site];
                    if (!(input >> image) || image < 0 || image >= code.n || seen[image])
                        throw std::runtime_error("symmetry generator is not a permutation");
                    seen[image] = true;
                    if ((site < anchor) != (image < anchor))
                        throw std::runtime_error("symmetry generator does not preserve the LP anchor block");
                }
                auto image = [&](const Word &row) {
                    Word result{};
                    for (int site = 0; site < code.n; ++site)
                        if (bit(row, site)) toggle(result, permutation[site]);
                    return result;
                };
                for (const auto &row : code.H)
                    if (checks.nontrivial(image(row)))
                        throw std::runtime_error("symmetry does not preserve the check space");
                for (const auto &row : code.G)
                    if (code.basis.nontrivial(image(row)))
                        throw std::runtime_error("symmetry does not preserve the stabilizer space");
                for (int site = 0; site < code.n; ++site) {
                    int a = find(site), b = find(permutation[site]);
                    parent[std::max(a, b)] = std::min(a, b);
                }
            }
            std::string extra;
            if (input >> extra) throw std::runtime_error("unexpected data after symmetry generators");
        }
        for (int site = 0; site < code.n; ++site)
            if (find(site) == site) representatives.push_back(site);
    }

    std::string metadata(int anchor = 0) const {
        if (!explicit_generators) return "";
        std::ostringstream out;
        out << ",\"symmetry_generators\":" << generator_count << ",\"root_representatives\":[";
        bool comma = false;
        for (int site : representatives) {
            if (site < anchor) continue;
            if (comma) out << ',';
            out << site;
            comma = true;
        }
        out << ']';
        return out.str();
    }
};
