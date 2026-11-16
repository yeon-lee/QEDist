// Exhaustive irreducible-support search. See README.txt for the proof of
// completeness, the coset-leader pruning rule, and the shard partition.
#include "common.hpp"
#include "symmetry.hpp"

// Every word in ker(H) has even Hamming weight exactly when the all-ones
// functional is a sum of check rows. Track that sum so a separate checker
// can validate the positive claim using XOR alone.
struct KernelParity {
    bool even=false;
    Vector<int> certificate_rows;
    explicit KernelParity(const BinaryCode &c) {
        Vector<Word> rows, combinations;
        Vector<int> pivots;
        const int coefficient_words=(size_t(c.m)+63)/64;
        for(int i=0;i<c.m;++i){
            Word row=c.H[i], combination(coefficient_words);toggle(combination,i);
            for(size_t j=0;j<rows.size();++j)if(bit(row,pivots[j])){
                xorin(row,rows[j],c.words);
                xorin(combination,combinations[j],coefficient_words);
            }
            for(int p=0;p<c.n;++p)if(bit(row,p)){
                rows.push_back(row);combinations.push_back(combination);pivots.push_back(p);break;
            }
        }
        Word ones(c.words), combination(coefficient_words);
        for(int j=0;j<c.n;++j)toggle(ones,j);
        for(size_t j=0;j<rows.size();++j)if(bit(ones,pivots[j])){
            xorin(ones,rows[j],c.words);
            xorin(combination,combinations[j],coefficient_words);
        }
        even=weight(ones,c.words)==0;
        if(even)for(int i=0;i<c.m;++i)if(bit(combination,i))certificate_rows.push_back(i);
    }
};


struct Exact {
    BinaryCode c;
    KernelParity parity;
    int P, W, effective_W, root, begin, end;
    int maxdeg = 0, maxrow = 0, sw = 0, bad = 0;
    bool use_parity = true, found = false, incomplete = false, use_coset = true;
    bool proposed_additions = false, hashed = false;
    double seconds;
    uint64_t cap, nodes = 0, coset_prunes = 0, pack_prunes = 0;
    uint64_t proposed_candidates = 0, proposed_prunes = 0, proposed_prefix_prunes = 0;
    int repair_depth = 0;
    uint64_t repair_calls = 0, repair_changes = 0;
    int shard = 0, shards = 1, split_weight = 1, roots_completed = 0;
    uint64_t frontier_seen = 0, frontier_owned = 0, frontier_digest = 0, common_nodes = 0;
    std::string symmetry_file;
    Word selected;
    Vector<uint64_t> available, initial_available, syndrome;
    Vector<size_t> offsets;
    Vector<int> overlap, index;
    Vector<unsigned char> forbidden;
    struct Edge { size_t word; uint64_t mask; };
    Vector<Vector<Edge>> edges;
    Vector<uint32_t> used_epoch, fractional_mark;
    uint32_t packing_epoch = 0, fractional_epoch = 0;
    Vector<int> fractional_load, fractional_weights;
    int fractional_mode = 0;
    uint64_t fractional_calls = 0, fractional_prunes = 0;
    std::ofstream fractional_proofs;
    uint64_t fractional_proof_limit = 64, fractional_proofs_written = 0;
    std::chrono::steady_clock::time_point start;

    // Pruning scratch is reused after entering each child. Only branch choices
    // and undo information survive in a frame, keeping deep searches compact.
    Vector<int> ids, next, head, tail;
    struct Option { int v, score; bool impossible; };
    struct Frame {
        Vector<Option> options;
        size_t next_option = 0, blocked = 0;
        int child = -1;
        uint64_t key = 0;
    };
    Vector<Frame> frames;

    Exact(const std::string &path, int p, int w, double sec, int r, int b, int e,
          uint64_t node_cap, bool prune, bool parity_enabled)
        : c(path), parity(c), P(p), W(w),
          effective_W(w - (parity_enabled && parity.even && (w % 2))),
          root(r), begin(b), end(e), use_parity(parity_enabled), use_coset(prune),
          seconds(sec), cap(node_cap), selected(c.words) {
        if (W < 1 || P < 1 || c.n % P || root < 0 || root >= c.n / P || begin < 0 || end <= begin)
            throw std::runtime_error("invalid exact search parameters");
        c.validate_translation(P);
        edges.resize(c.n);
        syndrome.resize((size_t(c.m) + 63) / 64);
        forbidden.resize(c.n); overlap.resize(c.g); index.resize(c.m);
        for (int row = 0; row < c.m; ++row) {
            int degree = c.hr[row].size();
            maxrow = std::max(maxrow, degree);
            offsets.push_back(initial_available.size());
            for (size_t first = 0; first < c.hr[row].size(); first += 64) {
                size_t count = std::min(size_t(64), c.hr[row].size() - first);
                initial_available.push_back(count == 64 ? ~uint64_t(0) : ((uint64_t(1) << count) - 1));
            }
            for (size_t j = 0; j < c.hr[row].size(); ++j)
                edges[c.hr[row][j]].push_back({offsets.back() + j / 64, uint64_t(1) << (j % 64)});
        }
        offsets.push_back(initial_available.size());
        available = initial_available;
        used_epoch.resize(c.n); fractional_mark.resize(c.n); fractional_load.resize(c.n);
        fractional_weights.resize(c.m);
        ids.resize(c.m); next.resize(c.m);
        head.resize(size_t(maxrow) + 1); tail.resize(size_t(maxrow) + 1);
        for (const auto &checks : c.vc) maxdeg = std::max(maxdeg, int(checks.size()));
    }
    AvailableSites sites(int row) const {
        size_t words = offsets[row + 1] - offsets[row];
        return {c.hr[row], words ? available.data() + offsets[row] : nullptr, words};
    }
    bool unsatisfied(int row) const { return (syndrome[row / 64] >> (row % 64)) & 1; }
    void block(int site) {
        forbidden[site] = 1;
        for (const auto &edge : edges[site]) {
            available[edge.word] ^= edge.mask;
        }
    }
    void unblock(int site) {
        forbidden[site] = 0;
        for (const auto &edge : edges[site]) {
            available[edge.word] ^= edge.mask;
        }
    }
    void flip(int site, int delta) {
        toggle(selected, site);
        for (int row : c.vc[site]) {
            sw += unsatisfied(row) ? -1 : 1;
            syndrome[row / 64] ^= uint64_t(1) << (row % 64);
        }
        if (use_coset) for (int row : c.vg[site]) {
            bad -= (2LL * overlap[row] > int64_t(c.gr[row].size()));
            overlap[row] += delta;
            bad += (2LL * overlap[row] > int64_t(c.gr[row].size()));
        }
    }
    int repair_check(int best, int wt, int degree) {
        if (!repair_depth || wt > repair_depth || next[head[degree]] < 0) return best;
        ++repair_calls;
        int winner = best;
        int64_t bestscore = -1;
        for (int k = head[degree]; k >= 0; k = next[k]) {
            int row = ids[k];
            int64_t score = 0;
            for (int site : sites(row)) for (int check : c.vc[site]) score += unsatisfied(check);
            if (score > bestscore) { winner = row; bestscore = score; }
        }
        repair_changes += winner != best;
        return winner;
    }
    void fractional_certificate(int wt, int budget, int count, int denominator) {
        if (!fractional_proofs.is_open() || fractional_proofs_written >= fractional_proof_limit) return;
        ++fractional_proofs_written;
        fractional_proofs << "{\"node\":" << nodes << ",\"wt\":" << wt << ",\"K\":" << effective_W
            << ",\"budget\":" << budget << ",\"sw\":" << sw << ",\"S\":[";
        bool comma = false;
        for (int site = 0; site < c.n; ++site) if (bit(selected, site)) {
            if (comma) fractional_proofs << ',';
            fractional_proofs << site; comma = true;
        }
        fractional_proofs << "],\"unavailable\":["; comma = false;
        for (int site = 0; site < c.n; ++site) if (forbidden[site]) {
            if (comma) fractional_proofs << ',';
            fractional_proofs << site; comma = true;
        }
        fractional_proofs << "],\"odd_rows\":[";
        for (int i = 0; i < count; ++i) { if (i) fractional_proofs << ','; fractional_proofs << ids[i]; }
        fractional_proofs << "],\"available_rows\":[";
        for (int i = 0; i < count; ++i) {
            if (i) fractional_proofs << ',';
            fractional_proofs << '['; comma = false;
            for (int site : sites(ids[i])) {
                if (comma) fractional_proofs << ',';
                fractional_proofs << site; comma = true;
            }
            fractional_proofs << ']';
        }
        fractional_proofs << "],\"certificate\":{\"denominator\":" << denominator << ",\"row_ids\":[";
        for (int i = 0; i < count; ++i) { if (i) fractional_proofs << ','; fractional_proofs << ids[i]; }
        fractional_proofs << "],\"weights\":[";
        for (int i = 0; i < count; ++i) { if (i) fractional_proofs << ','; fractional_proofs << fractional_weights[ids[i]]; }
        fractional_proofs << "]}}\n";
    }
#include "even_methods.inc"
    static bool independent(uint64_t vertices, int need, const uint64_t *adjacency, int &steps) {
        if (need <= 0) return true;
        if (__builtin_popcountll(vertices) < need || ++steps > 120) return false;
        int selected_vertex = -1, minimum = 100;
        uint64_t remaining = vertices;
        while (remaining) {
            int vertex = __builtin_ctzll(remaining); remaining &= remaining - 1;
            int degree = __builtin_popcountll(adjacency[vertex] & vertices);
            if (degree < minimum) { selected_vertex = vertex; minimum = degree; if (degree <= 1) break; }
        }
        if (minimum <= 2) return independent(vertices & ~adjacency[selected_vertex], need - 1, adjacency, steps);
        return independent(vertices & ~adjacency[selected_vertex], need - 1, adjacency, steps) ||
               independent(vertices & ~(uint64_t(1) << selected_vertex), need, adjacency, steps);
    }
    static uint64_t mix(uint64_t x) {
        x += 0x9e3779b97f4a7c15ULL;
        x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
        x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }
    bool prepare_node(int wt, uint64_t key) {
        ++nodes;
        if (nodes > cap || ((nodes == 1 || (nodes & 16383) == 0) &&
                           (stopped || elapsed(start) >= seconds))) {
            incomplete = true;
            return false;
        }
        if (hashed && wt <= split_weight) ++common_nodes;
        if (hashed && wt == split_weight) {
            ++frontier_seen; frontier_digest ^= mix(key);
            if (key % uint64_t(shards) != uint64_t(shard)) return false;
            ++frontier_owned;
        }
        if (bad) { ++coset_prunes; return false; }
        if (!sw) {
            if (c.basis.nontrivial(selected)) {
                if (!c.kernel(selected)) throw std::runtime_error("internal syndrome mismatch");
                found = true;
                std::cout << "{\"event\":\"witness\",\"weight\":" << wt << ",\"support\":";
                print_support(selected, c.n);
                std::cout << "}\n" << std::flush;
            }
            return false;
        }
        int budget = std::min(effective_W, c.n) - wt;
        if (budget <= 0 || int64_t(sw) > int64_t(budget) * maxdeg) return false;
        int count = 0, best = -1, minavail = maxrow;
        std::fill(head.begin(), head.end(), -1);
        std::fill(tail.begin(), tail.end(), -1);
        for (size_t k = 0; k < syndrome.size(); ++k) {
            uint64_t mask = syndrome[k];
            while (mask) {
                int row = int(64 * k + __builtin_ctzll(mask)); mask &= mask - 1;
                int degree = 0;
                for (size_t word = offsets[row]; word < offsets[row + 1]; ++word)
                    degree += __builtin_popcountll(available[word]);
                if (!degree) return false;
                ids[count] = row; next[count] = -1;
                if (head[degree] < 0) head[degree] = count;
                else next[tail[degree]] = count;
                tail[degree] = count++;
                if (best < 0 || degree < minavail) { minavail = degree; best = row; }
            }
        }
        int64_t completion_total = 0;
        int completion_denominator = 0;
        if (sw > budget) {
            if (++packing_epoch == 0) { std::fill(used_epoch.begin(), used_epoch.end(), 0); packing_epoch = 1; }
            int packing = 0;
            for (size_t degree = minavail; degree <= size_t(maxrow); ++degree) for (int k = head[degree]; k >= 0; k = next[k]) {
                int row = ids[k];
                bool intersects = false;
                for (int site : sites(row)) if (used_epoch[site] == packing_epoch) { intersects = true; break; }
                if (!intersects) {
                    if (++packing > budget) { ++pack_prunes; return false; }
                    for (int site : sites(row)) used_epoch[site] = packing_epoch;
                }
            }
            if (fractional_mode) {
                ++fractional_calls;
                if (++fractional_epoch == 0) { std::fill(fractional_mark.begin(), fractional_mark.end(), 0); fractional_epoch = 1; }
                if (fractional_proofs.is_open() || even_proofs.is_open())
                    for (int i = 0; i < count; ++i) fractional_weights[ids[i]] = 0;
                if (fractional_mode == -1) {
                    int maximum = 0;
                    for (int i = 0; i < count; ++i) for (int site : sites(ids[i])) {
                        if (fractional_mark[site] != fractional_epoch) { fractional_mark[site] = fractional_epoch; fractional_load[site] = 0; }
                        maximum = std::max(maximum, ++fractional_load[site]);
                    }
                    completion_total = sw; completion_denominator = maximum;
                    if (int64_t(sw) > int64_t(maximum) * budget) {
                        ++fractional_prunes;
                        if (fractional_proofs.is_open()) {
                            for (int i = 0; i < count; ++i) fractional_weights[ids[i]] = 1;
                            fractional_certificate(wt, budget, count, maximum);
                        }
                        return false;
                    }
                } else {
                    int denominator = fractional_mode;
                    int64_t total = 0;
                    for (int pass = 0; pass < denominator; ++pass) {
                        bool changed = false;
                        for (size_t degree = minavail; degree <= size_t(maxrow); ++degree) for (int k = head[degree]; k >= 0; k = next[k]) {
                            int row = ids[k];
                            bool fits = true;
                            for (int site : sites(row)) if (fractional_mark[site] == fractional_epoch && fractional_load[site] >= denominator) { fits = false; break; }
                            if (!fits) continue;
                            changed = true; ++total;
                            if (fractional_proofs.is_open() || even_proofs.is_open()) ++fractional_weights[row];
                            if (total > int64_t(denominator) * budget) { ++fractional_prunes; fractional_certificate(wt, budget, count, denominator); return false; }
                            for (int site : sites(row)) {
                                if (fractional_mark[site] != fractional_epoch) { fractional_mark[site] = fractional_epoch; fractional_load[site] = 0; }
                                ++fractional_load[site];
                            }
                        }
                        if (!changed) break;
                    }
                    if (even_repair_cap && even_bound(wt, budget, count, minavail, denominator, total)) return false;
                    completion_total = total; completion_denominator = denominator;
                }
            }
            if (sw <= 63 && int64_t(packing) + 3 > budget) {
                uint64_t adjacency[63];
                for (int i = 0; i < count; ++i) index[ids[i]] = i;
                for (int i = 0; i < count; ++i) {
                    adjacency[i] = uint64_t(1) << i;
                    for (int site : sites(ids[i])) for (int row : c.vc[site])
                        if (unsatisfied(row)) adjacency[i] |= uint64_t(1) << index[row];
                }
                int steps = 0;
                if (independent((uint64_t(1) << count) - 1, budget + 1, adjacency, steps)) { ++pack_prunes; return false; }
            }
        }
        best = repair_check(best, wt, minavail);
        if (frames.size() <= size_t(wt)) frames.resize(size_t(wt) + 1);
        Frame &frame = frames[wt];
        frame.options.clear(); frame.next_option = frame.blocked = 0; frame.child = -1; frame.key = key;
        for (int site : sites(best)) {
            int score = 0;
            for (int check : c.vc[site]) score += unsatisfied(check);
            int load = fractional_mark[site] == fractional_epoch ? fractional_load[site] : 0;
            bool impossible = proposed_additions && completion_denominator > 0 &&
                completion_total - load > int64_t(completion_denominator) * (budget - 1);
            if (impossible) ++proposed_candidates;
            frame.options.push_back({site, score, impossible});
        }
        std::sort(frame.options.begin(), frame.options.end(), [](const Option &a, const Option &b) {
            return a.score != b.score ? a.score > b.score : a.v < b.v;
        });
        return true;
    }
    void dfs(int wt, uint64_t key = 0) {
        if (!prepare_node(wt, key)) return;
        int depth = wt;
        while (depth >= wt) {
            Frame &frame = frames[depth];
            if (frame.child >= 0) { flip(frame.child, -1); frame.child = -1; }
            if (found || incomplete || frame.next_option == frame.options.size() ||
                (depth == 1 && frame.next_option >= size_t(end))) {
                for (size_t j = 0; j < frame.blocked; ++j) unblock(frame.options[j].v);
                --depth;
                continue;
            }
            size_t option_index = frame.next_option++;
            Option option = frame.options[option_index];
            block(option.v); ++frame.blocked;
            if (depth == 1 && option_index < size_t(begin)) continue;
            if (option.impossible) {
                ++proposed_prunes;
                if (hashed && depth < split_weight) ++proposed_prefix_prunes;
                continue;
            }
            uint64_t child_key = hashed && depth < split_weight ? mix(frame.key ^ uint64_t(option.v)) : frame.key;
            frame.child = option.v;
            flip(option.v, 1);
            if (prepare_node(depth + 1, child_key)) ++depth;
        }
    }
    int anchor_site = 0;
    int run(){
        // Every mixed support has a first occupied orbit in this suffix.
        // Qubits before the suffix stay available throughout every branch.
        if (anchor_site < 0 || anchor_site >= c.n || anchor_site % P != 0)
            throw std::runtime_error("anchor-site must begin a physical orbit");
        SymmetryRoots symmetry(c, P, symmetry_file, anchor_site);
        int first_orbit = std::lower_bound(symmetry.representatives.begin(),
            symmetry.representatives.end(), anchor_site) - symmetry.representatives.begin();
        if (root >= int(symmetry.representatives.size()))
            throw std::runtime_error("root exceeds the number of symmetry orbits");
        if (!hashed && root < first_orbit)
            throw std::runtime_error("selected root is outside the anchoring suffix");
        start=std::chrono::steady_clock::now();int first=hashed?first_orbit:root,last=hashed?int(symmetry.representatives.size()):root+1;
        if(effective_W==0)roots_completed=last-first;
        else for(int r=first;r<last;++r){
            std::fill(selected.begin(),selected.end(),0);sw=bad=0;std::fill(forbidden.begin(),forbidden.end(),0);std::fill(syndrome.begin(),syndrome.end(),0);std::fill(overlap.begin(),overlap.end(),0);
            available=initial_available;
            int v=symmetry.representatives[r];for(int j=anchor_site;j<=v;++j)block(j);flip(v,1);dfs(1,mix(uint64_t(r)));flip(v,-1);
            if(found||incomplete)break;++roots_completed;
        }
        std::cout<<"{\"event\":\"result\",\"status\":\""<<(found?"witness":incomplete?"incomplete":"excluded")
          <<"\",\"W\":"<<W<<",\"root\":"<<root<<",\"branch_begin\":"<<begin<<",\"branch_end\":"<<end
          <<",\"anchor_site\":"<<anchor_site<<",\"effective_W\":"<<effective_W<<",\"parity_cutoff_enabled\":"<<(use_parity?"true":"false")
          <<",\"kernel_even\":"<<(parity.even?"true":"false")<<",\"parity_trivial_exclusion\":"<<(effective_W==0?"true":"false")
          <<",\"parity_certificate_rows\":[";for(size_t i=0;i<parity.certificate_rows.size();++i){if(i)std::cout<<',';std::cout<<parity.certificate_rows[i];}std::cout<<']'
          <<",\"coset_pruning\":"<<(use_coset?"true":"false")<<",\"nodes\":"<<nodes<<",\"coset_prunes\":"<<coset_prunes
          <<",\"even_repair_cap\":"<<even_repair_cap<<",\"even_calls\":"<<even_calls<<",\"even_attempts\":"<<even_attempts<<",\"even_successes\":"<<even_successes<<",\"even_prunes\":"<<even_prunes
          <<",\"proposed_additions\":"<<(proposed_additions?"true":"false")
          <<",\"proposed_candidates\":"<<proposed_candidates
          <<",\"proposed_prunes\":"<<proposed_prunes
          <<",\"proposed_prefix_prunes\":"<<proposed_prefix_prunes
          <<",\"packing_prunes\":"<<pack_prunes<<",\"repair_depth\":"<<repair_depth<<",\"repair_calls\":"<<repair_calls<<",\"repair_changes\":"<<repair_changes<<",\"fractional_placement\":\"before_mis\",\"fractional_mode\":"<<fractional_mode<<",\"fractional_calls\":"<<fractional_calls<<",\"fractional_prunes\":"<<fractional_prunes<<",\"seconds\":"<<elapsed(start)
          <<",\"partition\":\""<<(hashed?"hash_prefix_v1":"root_branch_v1")<<"\",\"shard\":"<<shard<<",\"shards\":"<<shards<<",\"split_weight\":"<<split_weight
          <<",\"roots_completed\":"<<roots_completed<<",\"frontier_seen\":"<<frontier_seen<<",\"frontier_owned\":"<<frontier_owned
          <<",\"frontier_digest\":\""<<frontier_digest<<"\",\"common_nodes\":"<<common_nodes<<symmetry.metadata(anchor_site)<<"}\n"<<std::flush;
        return found?10:incomplete?75:0;
    }
};
int main(int argc,char **argv){try{
    if(argc<9){std::cerr<<"exact matrix P W seconds root branch_begin branch_end nodecap [no-coset]\n"
      <<"exact matrix P W seconds --shard id count split_weight nodecap [no-coset]\n";return 2;}
    std::signal(SIGTERM,stop_handler);std::signal(SIGINT,stop_handler);
    int p=std::stoi(argv[2]);if(p<1)throw std::runtime_error("invalid P");
    bool hashed=std::string(argv[5])=="--shard";
    if(hashed&&argc<10)throw std::runtime_error("missing shard parameters");
    bool proposed_additions = false;
    bool prune=true,parity_enabled=true;int repair_depth=0;int fractional_mode=0;int even_repair_cap=0;std::string fractional_file,even_file,symmetry_file;
    int anchor_site = 0;
    for(int i=hashed?10:9;i<argc;++i){
        std::string option=argv[i];
        if(option=="no-coset")prune=false;
        else if(option=="proposed-additions=on")proposed_additions=true;
        else if(option=="proposed-additions=off")proposed_additions=false;
        else if(option.rfind("symmetry-file=",0)==0) {
            symmetry_file=option.substr(14);
            if(symmetry_file.empty())throw std::runtime_error("empty symmetry file path");
        }
        else if (option.rfind("anchor-site=", 0) == 0) {
            const auto value = option.substr(12);
            size_t consumed = 0;
            anchor_site = std::stoi(value, &consumed);
            if (consumed != value.size()) throw std::runtime_error("invalid anchor-site");
        }
        else if(option.rfind("even-repairs=",0)==0){even_repair_cap=std::stoi(option.substr(13));if(even_repair_cap<0||even_repair_cap>8)throw std::runtime_error("invalid even repair cap");}
        else if(option.rfind("even-proofs=",0)==0)even_file=option.substr(12);
        else if(option=="fractional=off")fractional_mode=0;
        else if(option=="fractional=2")fractional_mode=2;
        else if(option=="fractional=4")fractional_mode=4;
        else if(option=="fractional=uniform")fractional_mode=-1;
        else if(option.rfind("fractional-proofs=",0)==0)fractional_file=option.substr(18);
        else if(option.rfind("memory-bytes=",0)==0)set_memory_budget(option.substr(13));
        else if(option.rfind("repair-depth=",0)==0){repair_depth=std::stoi(option.substr(13));if(repair_depth<0)throw std::runtime_error("invalid repair depth");}
        else throw std::runtime_error("unknown option: "+option);
    }
    if(even_repair_cap&&fractional_mode<=0)throw std::runtime_error("even repairs require fractional=2 or4");
    Exact search(argv[1],p,std::stoi(argv[3]),std::stod(argv[4]),hashed?0:std::stoi(argv[5]),hashed?0:std::stoi(argv[6]),hashed?std::numeric_limits<int>::max():std::stoi(argv[7]),std::stoull(argv[hashed?9:8]),prune,parity_enabled);
    if(hashed){search.hashed=true;search.shard=std::stoi(argv[6]);search.shards=std::stoi(argv[7]);search.split_weight=std::stoi(argv[8]);
        if(search.shards<1||search.shard<0||search.shard>=search.shards||search.split_weight<1||search.split_weight>search.W)throw std::runtime_error("invalid shard partition");}
    search.anchor_site=anchor_site;
    search.proposed_additions = proposed_additions;
    search.symmetry_file=symmetry_file;
    search.fractional_mode=fractional_mode;search.repair_depth=repair_depth;search.even_repair_cap=even_repair_cap;
    if(!even_file.empty()){search.even_proofs.open(even_file);if(!search.even_proofs)throw std::runtime_error("cannot open even proof trace");}
    if(!fractional_file.empty()){search.fractional_proofs.open(fractional_file);if(!search.fractional_proofs)throw std::runtime_error("cannot open fractional proof trace");}
    return search.run();
}catch(const std::bad_alloc &){report_allocation_failure();return 75;}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
