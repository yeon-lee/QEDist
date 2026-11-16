    int even_repair_cap = 0;
    uint64_t even_calls = 0, even_attempts = 0, even_successes = 0, even_prunes = 0;
    std::ofstream even_proofs;
    uint64_t even_proofs_written = 0;
    Vector<int> even_rows, even_vertices, changed_vertices, changed_deltas;
    Vector<int> overloaded_vertices, trial_rows, trial_vertices;

    int even_load(int site) const {
        return fractional_mark[site] == fractional_epoch ? fractional_load[site] : 0;
    }
    void even_add(int site, int delta) {
        if (fractional_mark[site] != fractional_epoch) {
            fractional_mark[site] = fractional_epoch;
            fractional_load[site] = 0;
        }
        fractional_load[site] += delta;
    }
    void even_certificate(int wt, int budget, int count, int denominator) {
        if (!even_proofs.is_open() || even_proofs_written >= 64) return;
        ++even_proofs_written;
        even_proofs << "{\"node\":" << nodes << ",\"wt\":" << wt << ",\"K\":" << effective_W
                    << ",\"budget\":" << budget << ",\"sw\":" << sw << ",\"S\":[";
        bool comma = false;
        for (int site = 0; site < c.n; ++site) if (bit(selected, site)) {
            if (comma) even_proofs << ',';
            even_proofs << site; comma = true;
        }
        even_proofs << "],\"unavailable\":["; comma = false;
        for (int site = 0; site < c.n; ++site) if (forbidden[site]) {
            if (comma) even_proofs << ',';
            even_proofs << site; comma = true;
        }
        even_proofs << "],\"odd_rows\":[";
        for (int i = 0; i < count; ++i) { if (i) even_proofs << ','; even_proofs << ids[i]; }
        even_proofs << "],\"available_rows\":[";
        for (int i = 0; i < count; ++i) {
            if (i) even_proofs << ',';
            even_proofs << '['; comma = false;
            for (int site : sites(ids[i])) {
                if (comma) even_proofs << ',';
                even_proofs << site; comma = true;
            }
            even_proofs << ']';
        }
        even_proofs << "],\"certificate\":{\"denominator\":" << denominator << ",\"odd_terms\":[";
        for (int i = 0; i < count; ++i) {
            if (i) even_proofs << ',';
            even_proofs << '[' << ids[i] << ',' << fractional_weights[ids[i]] << ']';
        }
        even_proofs << "],\"even_terms\":[";
        for (size_t i = 0; i < even_rows.size(); ++i) {
            if (i) even_proofs << ',';
            even_proofs << '[' << even_rows[i] << ',' << even_vertices[i] << ",1]";
        }
        even_proofs << "]}}\n";
    }
    bool even_bound(int wt, int budget, int count, int minavail, int denominator, int64_t &total) {
        ++even_calls;
        int attempts = 0;
        even_rows.clear(); even_vertices.clear();
        for (size_t degree = minavail; degree <= size_t(maxrow); ++degree) for (int k = head[degree]; k >= 0; k = next[k]) {
            if (attempts >= 16) return false;
            if (total + std::min(16 - attempts, count - attempts) <= int64_t(denominator) * budget) return false;
            ++attempts; ++even_attempts;
            int row = ids[k];
            changed_vertices.clear(); changed_deltas.clear(); overloaded_vertices.clear();
            trial_rows.clear(); trial_vertices.clear();
            auto change = [&](int site, int delta) {
                even_add(site, delta);
                changed_vertices.push_back(site); changed_deltas.push_back(delta);
            };
            for (int site : sites(row)) {
                change(site, 1);
                if (even_load(site) > denominator) overloaded_vertices.push_back(site);
            }
            bool ok = overloaded_vertices.size() <= size_t(even_repair_cap);
            for (int site : overloaded_vertices) {
                if (!ok) break;
                int repair = -1;
                for (int check : c.vc[site]) if (!unsatisfied(check)) {
                    bool fits = true;
                    for (int other : sites(check)) if (other != site && even_load(other) >= denominator) { fits = false; break; }
                    if (fits) { repair = check; break; }
                }
                if (repair < 0) { ok = false; break; }
                trial_rows.push_back(repair); trial_vertices.push_back(site);
                for (int other : sites(repair)) change(other, other == site ? -1 : 1);
            }
            if (!ok) {
                for (size_t i = changed_vertices.size(); i; --i) even_add(changed_vertices[i - 1], -changed_deltas[i - 1]);
                continue;
            }
            ++even_successes; ++total;
            if (even_proofs.is_open()) ++fractional_weights[row];
            even_rows.insert(even_rows.end(), trial_rows.begin(), trial_rows.end());
            even_vertices.insert(even_vertices.end(), trial_vertices.begin(), trial_vertices.end());
            if (total > int64_t(denominator) * budget) {
                ++even_prunes; even_certificate(wt, budget, count, denominator); return true;
            }
        }
        return false;
    }
