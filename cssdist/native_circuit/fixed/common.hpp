#pragma once
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cctype>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <stdexcept>
#include <utility>
#include <vector>

inline volatile std::sig_atomic_t stopped=0;
inline void stop_handler(int){stopped=1;}
inline double elapsed(std::chrono::steady_clock::time_point t){return std::chrono::duration<double>(std::chrono::steady_clock::now()-t).count();}
inline void numeric_text(const std::string &s){if(s.empty()||std::any_of(s.begin(),s.end(),[](unsigned char c){return std::isspace(c);}))throw std::runtime_error("invalid numeric argument");}
inline int integer_argument(const std::string &s){numeric_text(s);size_t p=0;long long v=std::stoll(s,&p);if(p!=s.size()||v<INT32_MIN||v>INT32_MAX)throw std::runtime_error("invalid integer argument: "+s);return int(v);}
inline uint64_t unsigned_argument(const std::string &s){numeric_text(s);if(s[0]=='-')throw std::runtime_error("negative unsigned argument");size_t p=0;uint64_t v=std::stoull(s,&p);if(p!=s.size())throw std::runtime_error("invalid unsigned argument: "+s);return v;}
inline double real_argument(const std::string &s){numeric_text(s);size_t p=0;double v=std::stod(s,&p);if(p!=s.size()||!std::isfinite(v))throw std::runtime_error("invalid real argument: "+s);return v;}

// Sparse rows and dynamically sized row-local availability masks. Unlike the
// frozen CSS backend, neither the number of mechanisms nor detector degree has
// a compile-time bound. Dimensions must fit signed 32-bit coordinate indices.
struct CircuitModel {
    int n=0,m=0,o=0,g=0,maxrow=0,maxdegree=0;
    std::vector<std::vector<int>> D,O,K,vd,vo,vk;
    struct Edge { int row; size_t word; uint64_t bit; };
    std::vector<std::vector<Edge>> edges;
    std::vector<size_t> offsets;
    std::vector<uint64_t> initial_available;

    static std::vector<int> readrow(std::istream &f,int n){
        long long weight;if(!(f>>weight)||weight<0||weight>n)throw std::runtime_error("invalid row length");
        std::vector<int> row;row.reserve(size_t(weight));int previous=-1;
        while(weight--){long long q;if(!(f>>q)||q<=previous||q>=n)throw std::runtime_error("row coordinates must be sorted, unique, and in range");row.push_back(int(q));previous=int(q);}
        return row;
    }
    explicit CircuitModel(const std::string &path){
        std::ifstream f(path);std::string magic;long long nn,mm,oo,gg;
        if(!(f>>magic>>nn>>mm>>oo>>gg)||magic!="QEDIST_CIRCUIT_V1"||nn<1||mm<0||oo<1||gg<0||nn>INT32_MAX||mm>INT32_MAX||oo>INT32_MAX||gg>INT32_MAX)
            throw std::runtime_error("invalid QEDIST_CIRCUIT_V1 header");
        // Guard obviously impossible headers before allocating. This is a
        // storage estimate, not the historical 8192-column/64-degree limit.
        if(192.L*nn+64.L*mm+40.L*oo+48.L*gg>8.L*1024*1024*1024)
            throw std::runtime_error("base model storage estimate exceeds 8 GiB safety guard");
        n=int(nn);m=int(mm);o=int(oo);g=int(gg);
        D.reserve(m);O.reserve(o);K.reserve(g);vd.resize(n);vo.resize(n);vk.resize(n);edges.resize(n);offsets.reserve(size_t(m)+1);
        for(int j=0;j<m;++j){
            D.push_back(readrow(f,n));offsets.push_back(initial_available.size());int degree=int(D.back().size());maxrow=std::max(maxrow,degree);
            for(int k=0;k<degree;k+=64){int bits=std::min(64,degree-k);initial_available.push_back(bits==64?~uint64_t(0):((uint64_t(1)<<bits)-1));}
            for(int k=0;k<degree;++k){int v=D.back()[k];vd[v].push_back(j);edges[v].push_back({j,offsets.back()+size_t(k/64),uint64_t(1)<<(k%64)});}
        }
        offsets.push_back(initial_available.size());
        for(int j=0;j<o;++j){O.push_back(readrow(f,n));for(int v:O.back())vo[v].push_back(j);}
        for(int j=0;j<g;++j){K.push_back(readrow(f,n));if(K.back().empty())throw std::runtime_error("empty neutral row");for(int v:K.back())vk[v].push_back(j);}
        std::string extra;if(f>>extra)throw std::runtime_error("trailing matrix data");
        for(const auto &rows:vd)maxdegree=std::max(maxdegree,int(rows.size()));
        // Every optional overlap-pruning row must preserve BOTH detector and
        // observable parity. No claim that K spans the neutral kernel is needed.
        std::vector<unsigned char> d(m),obs(o);int detector_count=0,observable_count=0;
        for(const auto &row:K){
            for(int v:row){for(int j:vd[v]){detector_count+=d[j]?-1:1;d[j]^=1;}for(int j:vo[v]){observable_count+=obs[j]?-1:1;obs[j]^=1;}}
            if(detector_count||observable_count)
                throw std::runtime_error("neutral row changes detector or observable parity");
        }
    }
    bool witness(const std::vector<unsigned char>&selected)const{
        for(const auto &row:D){int p=0;for(int v:row)p^=selected[v];if(p)return false;}
        for(const auto &row:O){int p=0;for(int v:row)p^=selected[v];if(p)return true;}
        return false;
    }
};
