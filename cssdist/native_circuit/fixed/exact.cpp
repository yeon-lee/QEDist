// Direct detector/observable circuit-distance search; see README.txt.
// Derived algorithmically from native_weighted8192, whose sources are frozen.
#include "common.hpp"

struct Search {
    CircuitModel c;
    int W,budget_limit,root_begin=0,root_end,roots_completed=0,sw=0,ow=0,bad=0;
    double seconds;uint64_t cap,nodes=0;
    bool weighted=true,neutral=true,found=false,timedout=false,node_limit=false,interrupted=false;
    int repair_depth=8,even_repair_cap=4;
    uint64_t neutral_prunes=0,packing_prunes=0,weighted_calls=0,weighted_prunes=0,even_calls=0,even_attempts=0,even_successes=0,even_prunes=0,repair_calls=0,repair_changes=0;
    std::vector<uint64_t> available,syndrome;
    std::vector<int> available_count,overlap,index;
    std::vector<unsigned char> forbidden,selected,observables;
    std::vector<uint32_t> used_epoch,load_epoch;uint32_t packing_epoch=0,fractional_epoch=0;
    std::vector<int> loads;
    struct Option {int v,score;};
    struct Workspace {
        std::vector<int> ids,next,head,tail,changed_v,changed_delta,over;
        std::vector<Option> options;
        void initialize(int m,int maxrow){if(head.empty()){ids.resize(m);next.resize(m);head.resize(size_t(maxrow)+1);tail.resize(size_t(maxrow)+1);options.reserve(maxrow);}}
    };
    std::vector<Workspace> work;
    std::chrono::steady_clock::time_point start;std::clock_t cpu_start;

    Search(const std::string &path,int cutoff,double sec,uint64_t nodecap):c(path),W(cutoff),budget_limit(std::min(cutoff,c.n)),root_end(c.n),seconds(sec),cap(nodecap){
        if(W<0||!std::isfinite(sec)||sec<0)throw std::runtime_error("invalid cutoff or seconds");
        // Recursion uses one C++ stack frame per occupied mechanism. Explicit
        // bound is on depth only, never on detector degree or model dimensions.
        if(budget_limit>512)throw std::runtime_error("cutoff above supported recursion depth 512");
        available=c.initial_available;available_count.resize(c.m);syndrome.resize((size_t(c.m)+63)/64);overlap.resize(c.g);index.resize(c.m);
        forbidden.resize(c.n);selected.resize(c.n);observables.resize(c.o);used_epoch.resize(c.n);load_epoch.resize(c.n);loads.resize(c.n);
        work.resize(size_t(budget_limit)+1);
    }
    bool incomplete()const{return timedout||node_limit||interrupted;}
    bool odd(int j)const{return (syndrome[j/64]>>(j%64))&1;}
    template<class F> void each(int j,F action)const{
        size_t begin=c.offsets[j],end=c.offsets[j+1];
        for(size_t k=begin;k<end;++k){uint64_t a=available[k];while(a){int b=__builtin_ctzll(a);a&=a-1;action(c.D[j][64*(k-begin)+b]);}}
    }
    void block(int v){forbidden[v]=1;for(auto edge:c.edges[v]){available[edge.word]^=edge.bit;--available_count[edge.row];}}
    void unblock(int v){forbidden[v]=0;for(auto edge:c.edges[v]){available[edge.word]^=edge.bit;++available_count[edge.row];}}
    void flip(int v,int delta){
        selected[v]^=1;for(int j:c.vd[v]){sw+=odd(j)?-1:1;syndrome[j/64]^=uint64_t(1)<<(j%64);}
        for(int j:c.vo[v]){ow+=observables[j]?-1:1;observables[j]^=1;}
        if(neutral)for(int j:c.vk[v]){bad-=(2*overlap[j]>int(c.K[j].size()));overlap[j]+=delta;bad+=(2*overlap[j]>int(c.K[j].size()));}
    }
    static bool independent(uint64_t a,int need,const uint64_t*adj,int &steps){
        if(need<=0)return true;if(__builtin_popcountll(a)<need||++steps>120)return false;
        int v=-1,mind=100;uint64_t tmp=a;
        while(tmp){int j=__builtin_ctzll(tmp);tmp&=tmp-1;int d=__builtin_popcountll(adj[j]&a);if(d<mind){v=j;mind=d;if(d<=1)break;}}
        if(mind<=2)return independent(a&~adj[v],need-1,adj,steps);
        return independent(a&~adj[v],need-1,adj,steps)||independent(a&~(uint64_t(1)<<v),need,adj,steps);
    }
    int load(int v)const{return load_epoch[v]==fractional_epoch?loads[v]:0;}
    void add_load(int v,int delta){if(load_epoch[v]!=fractional_epoch){load_epoch[v]=fractional_epoch;loads[v]=0;}loads[v]+=delta;}
    bool even_bound(int budget,int count,Workspace &f,int minavail,int denominator,int total){
        ++even_calls;int attempts=0;
        for(int degree=minavail;degree<=c.maxrow;++degree)for(int k=f.head[degree];k>=0;k=f.next[k]){
            if(attempts>=16)return false;
            if(total+std::min(16-attempts,count-attempts)<=denominator*budget)return false;
            ++attempts;++even_attempts;int row=f.ids[k];f.changed_v.clear();f.changed_delta.clear();f.over.clear();
            auto change=[&](int v,int delta){add_load(v,delta);f.changed_v.push_back(v);f.changed_delta.push_back(delta);};
            each(row,[&](int v){change(v,1);if(load(v)>denominator)f.over.push_back(v);});
            bool ok=int(f.over.size())<=even_repair_cap;
            for(int v:f.over){if(!ok)break;int repair=-1;
                for(int q:c.vd[v])if(!odd(q)){
                    bool fits=true;each(q,[&](int u){if(u!=v&&load(u)>=denominator)fits=false;});
                    if(fits){repair=q;break;}
                }
                if(repair<0){ok=false;break;}
                each(repair,[&](int u){change(u,u==v?-1:1);});
            }
            if(!ok){for(size_t a=f.changed_v.size();a;--a)add_load(f.changed_v[a-1],-f.changed_delta[a-1]);continue;}
            ++even_successes;++total;if(total>denominator*budget){++even_prunes;return true;}
        }
        return false;
    }
    int repair_check(int best,int wt,int degree,const Workspace &f){
        if(!repair_depth||wt>repair_depth||f.next[f.head[degree]]<0)return best;
        ++repair_calls;int winner=best,bestscore=-1;
        for(int k=f.head[degree];k>=0;k=f.next[k]){int j=f.ids[k],score=0;each(j,[&](int v){for(int row:c.vd[v])score+=odd(row);});if(score>bestscore){winner=j;bestscore=score;}}
        repair_changes+=winner!=best;return winner;
    }
    void dfs(int wt){
        ++nodes;if(nodes>cap){node_limit=true;return;}
        if(nodes==1||(nodes&4095)==0){if(stopped){interrupted=true;return;}if(elapsed(start)>=seconds){timedout=true;return;}}
        if(bad){++neutral_prunes;return;}
        if(!sw){if(ow){if(!c.witness(selected))throw std::runtime_error("internal witness mismatch");found=true;
            std::cout<<"{\"event\":\"witness\",\"weight\":"<<wt<<",\"support\":[";bool comma=false;
            for(int v=0;v<c.n;++v)if(selected[v]){if(comma)std::cout<<',';std::cout<<v;comma=true;}std::cout<<"]}\n"<<std::flush;
        }return;}
        int budget=budget_limit-wt;if(budget<=0||int64_t(sw)>int64_t(budget)*c.maxdegree)return;
        Workspace &f=work[wt];f.initialize(c.m,c.maxrow);std::fill(f.head.begin(),f.head.end(),-1);std::fill(f.tail.begin(),f.tail.end(),-1);
        int count=0,best=-1,minavail=c.maxrow+1;
        for(size_t k=0;k<syndrome.size();++k){uint64_t a=syndrome[k];while(a){int j=int(64*k)+__builtin_ctzll(a);a&=a-1;int degree=available_count[j];if(!degree)return;
            f.ids[count]=j;f.next[count]=-1;if(f.head[degree]<0)f.head[degree]=count;else f.next[f.tail[degree]]=count;f.tail[degree]=count++;
            if(degree<minavail){minavail=degree;best=j;}
        }}
        if(sw>budget){
            if(++packing_epoch==0){std::fill(used_epoch.begin(),used_epoch.end(),0);packing_epoch=1;}int packing=0;
            for(int degree=minavail;degree<=c.maxrow;++degree)for(int k=f.head[degree];k>=0;k=f.next[k]){
                int j=f.ids[k];bool intersects=false;each(j,[&](int v){if(used_epoch[v]==packing_epoch)intersects=true;});
                if(!intersects){if(++packing>budget){++packing_prunes;return;}each(j,[&](int v){used_epoch[v]=packing_epoch;});}
            }
            if(weighted){
                ++weighted_calls;if(++fractional_epoch==0){std::fill(load_epoch.begin(),load_epoch.end(),0);fractional_epoch=1;}
                const int denominator=2;int total=0;
                for(int pass=0;pass<denominator;++pass){bool changed=false;
                    for(int degree=minavail;degree<=c.maxrow;++degree)for(int k=f.head[degree];k>=0;k=f.next[k]){
                        int row=f.ids[k];bool fits=true;each(row,[&](int v){if(load(v)>=denominator)fits=false;});if(!fits)continue;
                        changed=true;if(++total>denominator*budget){++weighted_prunes;return;}each(row,[&](int v){add_load(v,1);});
                    }
                    if(!changed)break;
                }
                if(even_repair_cap&&even_bound(budget,count,f,minavail,denominator,total))return;
            }
            if(sw<=63&&packing+3>budget){
                uint64_t adj[63];for(int i=0;i<count;++i)index[f.ids[i]]=i;
                for(int i=0;i<count;++i){adj[i]=uint64_t(1)<<i;each(f.ids[i],[&](int v){for(int j:c.vd[v])if(odd(j))adj[i]|=uint64_t(1)<<index[j];});}
                int steps=0;if(independent((uint64_t(1)<<count)-1,budget+1,adj,steps)){++packing_prunes;return;}
            }
        }
        best=repair_check(best,wt,minavail,f);f.options.clear();
        each(best,[&](int v){int score=0;for(int j:c.vd[v])score+=odd(j);f.options.push_back({v,score});});
        std::sort(f.options.begin(),f.options.end(),[](Option a,Option b){return a.score!=b.score?a.score>b.score:a.v<b.v;});
        size_t blocked=0;for(const auto option:f.options){block(option.v);++blocked;flip(option.v,1);dfs(wt+1);flip(option.v,-1);if(found||incomplete())break;}
        for(size_t j=0;j<blocked;++j)unblock(f.options[j].v);
    }
    int run(){
        start=std::chrono::steady_clock::now();cpu_start=std::clock();
        if(root_begin<0||root_end<root_begin||root_end>c.n)throw std::runtime_error("invalid root range");
        // Blocking root prefixes partitions supports by their first mechanism.
        available=c.initial_available;for(int j=0;j<c.m;++j)available_count[j]=int(c.D[j].size());
        for(int v=0;v<root_begin;++v)block(v);
        if(budget_limit==0||c.o==0)roots_completed=root_end-root_begin;
        else for(int root=root_begin;root<root_end;++root){
            if(stopped){interrupted=true;break;}if(elapsed(start)>=seconds){timedout=true;break;}
            block(root);flip(root,1);dfs(1);flip(root,-1);if(found||incomplete())break;++roots_completed;
        }
        std::string status=found?"witness":timedout?"timeout":node_limit?"node_limit":interrupted?"interrupted":"excluded";
        bool complete=!found&&!incomplete()&&root_begin==0&&root_end==c.n&&roots_completed==c.n;
        std::cout<<"{\"event\":\"result\",\"status\":\""<<status<<"\",\"W\":"<<W<<",\"effective_W\":"<<budget_limit
            <<",\"complete\":"<<(complete?"true":"false")<<",\"timedout\":"<<(timedout?"true":"false")
            <<",\"mechanisms\":"<<c.n<<",\"detectors\":"<<c.m<<",\"observables\":"<<c.o<<",\"neutral_rows\":"<<c.g
            <<",\"max_detector_degree\":"<<c.maxrow<<",\"weighted\":"<<(weighted?"true":"false")<<",\"neutral_pruning\":"<<(neutral?"true":"false")
            <<",\"root_begin\":"<<root_begin<<",\"root_end\":"<<root_end<<",\"roots_total\":"<<c.n<<",\"roots_completed\":"<<roots_completed
            <<",\"nodes\":"<<nodes<<",\"neutral_prunes\":"<<neutral_prunes<<",\"packing_prunes\":"<<packing_prunes
            <<",\"weighted_calls\":"<<weighted_calls<<",\"weighted_prunes\":"<<weighted_prunes
            <<",\"even_calls\":"<<even_calls<<",\"even_attempts\":"<<even_attempts<<",\"even_successes\":"<<even_successes<<",\"even_prunes\":"<<even_prunes
            <<",\"repair_calls\":"<<repair_calls<<",\"repair_changes\":"<<repair_changes
            <<",\"search_seconds\":"<<elapsed(start)<<",\"cpu_seconds\":"<<double(std::clock()-cpu_start)/CLOCKS_PER_SEC<<"}\n"<<std::flush;
        return found?10:incomplete()?75:0;
    }
};

int main(int argc,char**argv){try{
    if(argc<5)throw std::runtime_error("usage: exact MODEL W SECONDS NODECAP [weighted=on|off] [neutral=on|off] [even-repairs=4] [repair-depth=8] [root-begin=0] [root-end=n]");
    std::signal(SIGTERM,stop_handler);std::signal(SIGINT,stop_handler);
    Search search(argv[1],integer_argument(argv[2]),real_argument(argv[3]),unsigned_argument(argv[4]));
    for(int i=5;i<argc;++i){std::string option=argv[i];
        if(option=="weighted=on")search.weighted=true;else if(option=="weighted=off")search.weighted=false;
        else if(option=="neutral=on")search.neutral=true;else if(option=="neutral=off")search.neutral=false;
        else if(option.rfind("even-repairs=",0)==0){search.even_repair_cap=integer_argument(option.substr(13));if(search.even_repair_cap<0||search.even_repair_cap>8)throw std::runtime_error("invalid even repair cap");}
        else if(option.rfind("repair-depth=",0)==0){search.repair_depth=integer_argument(option.substr(13));if(search.repair_depth<0||search.repair_depth>512)throw std::runtime_error("invalid repair depth");}
        else if(option.rfind("root-begin=",0)==0)search.root_begin=integer_argument(option.substr(11));
        else if(option.rfind("root-end=",0)==0)search.root_end=integer_argument(option.substr(9));
        else throw std::runtime_error("unknown option: "+option);
    }
    return search.run();
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
