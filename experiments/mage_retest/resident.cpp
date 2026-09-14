// Bounded model-only replay using the retained JohnTdi-patched llama.cpp APIs.
// No StreamMind gate, capture transport, prefix reuse, or cross-request history.
#include "llama.h"
#include "mtmd.h"
#include "mtmd-helper.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock;
static double ms(Clock::time_point t) { return std::chrono::duration<double,std::milli>(Clock::now()-t).count(); }
static void require(bool ok, const char * why) { if (!ok) { std::cerr << why << std::endl; std::exit(2); } }
static std::string escape(const std::string &s) {
    std::string out;
    for (unsigned char c:s) { switch(c) {
        case '\\': out+="\\\\"; break; case '"': out+="\\\""; break;
        case '\n': out+="\\n"; break; case '\r': out+="\\r"; break;
        case '\t': out+="\\t"; break; default: if(c>=32) out+=c;
    }} return out;
}
static std::string piece(const llama_vocab *v, llama_token t) {
    std::string out(256,'\0'); int n=llama_token_to_piece(v,t,out.data(),out.size(),0,true);
    if(n<0) { out.resize(-n); n=llama_token_to_piece(v,t,out.data(),out.size(),0,true); }
    require(n>=0,"token decode failed"); out.resize(n); return out;
}
int main(int argc,char **argv) {
    require(argc==4,"usage: resident backbone projector prompt.txt");
    std::ofstream("/proc/self/oom_score_adj") << "800";
    std::ifstream pf(argv[3]); std::stringstream ps; ps<<pf.rdbuf();
    require(pf.good() || pf.eof(),"prompt read failed");
    auto started=Clock::now(); llama_backend_init();
    auto mp=llama_model_default_params(); mp.n_gpu_layers=999;
    std::unique_ptr<llama_model,decltype(&llama_model_free)> model(llama_model_load_from_file(argv[1],mp),llama_model_free);
    require(bool(model),"model load failed");
    auto vp=mtmd_context_params_default(); vp.use_gpu=true; vp.print_timings=true; vp.n_threads=4;
    mtmd::context_ptr vision(mtmd_init_from_file(argv[2],model.get(),vp)); require(bool(vision),"vision load failed");
    auto cp=llama_context_default_params(); cp.n_ctx=8192; cp.n_batch=1024; cp.n_ubatch=256;
    cp.n_threads=cp.n_threads_batch=4; cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;
    std::unique_ptr<llama_context,decltype(&llama_free)> ctx(llama_init_from_model(model.get(),cp),llama_free);
    require(bool(ctx),"context init failed");
    std::cout<<"{\"event\":\"ready\",\"load_ms\":"<<ms(started)<<",\"n_ctx\":"<<llama_n_ctx(ctx.get())<<"}"<<std::endl;
    std::string line;
    while(std::getline(std::cin,line)) {
        if(line.empty()) continue;
        auto t=Clock::now(); llama_memory_clear(llama_get_memory(ctx.get()),true);
        std::istringstream paths(line); std::string path;
        std::vector<mtmd_bitmap*> owned; std::vector<const mtmd_bitmap*> bitmaps;
        std::string prompt="<|im_start|>user\n";
        while(std::getline(paths,path,'\t')) {
            auto media=mtmd_helper_bitmap_init_from_file(vision.get(),path.c_str(),false);
            require(media.bitmap!=nullptr,"bundle read failed"); owned.push_back(media.bitmap); bitmaps.push_back(media.bitmap);
            prompt+=std::string(mtmd_get_marker(vision.get()))+"\n";
        }
        prompt+=ps.str()+"<|im_end|>\n<|im_start|>assistant\n";
        mtmd_input_text input{prompt.data(),prompt.size(),false,true};
        mtmd::input_chunks_ptr chunks(mtmd_input_chunks_init());
        require(mtmd_tokenize(vision.get(),chunks.get(),&input,bitmaps.data(),bitmaps.size())==0,"tokenize failed");
        std::vector<const mtmd_input_chunk*> images; size_t total=0, visual=0;
        std::vector<int> frames; std::vector<double> seconds;
        for(size_t i=0;i<mtmd_input_chunks_size(chunks.get());++i) {
            auto c=mtmd_input_chunks_get(chunks.get(),i); auto n=mtmd_input_chunk_get_n_tokens(c); total+=n;
            if(mtmd_input_chunk_get_type(c)==MTMD_INPUT_CHUNK_TYPE_IMAGE) {
                images.push_back(c); visual+=n; int32_t f=-1; double s=0;
                require(mtmd_input_chunk_get_mage_timestamp_frame(c,&f),"missing frame");
                require(mtmd_input_chunk_get_mage_timestamp_seconds(c,&s),"missing timestamp"); frames.push_back(f); seconds.push_back(s);
            }
        }
        require(total+96<llama_n_ctx(ctx.get()),"input exceeds context");
        std::cout<<"{\"event\":\"input\",\"visual_tokens\":"<<visual<<",\"prompt_tokens\":"<<total<<",\"frames\":[";
        for(size_t i=0;i<frames.size();++i) std::cout<<(i?",":"")<<frames[i];
        std::cout<<"],\"seconds\":["; for(size_t i=0;i<seconds.size();++i) std::cout<<(i?",":"")<<seconds[i];
        std::cout<<"]}"<<std::endl;
        auto tv=Clock::now(); std::vector<std::vector<float>> encoded;
        for(size_t first=0;first<images.size();) {
            mtmd::batch_ptr batch(mtmd_batch_init(vision.get())); size_t last=first;
            for(;last<images.size();++last) { int rc=mtmd_batch_add_chunk(batch.get(),images[last]); if(rc) {require(last>first,"batch add failed");break;} }
            require(mtmd_batch_encode(batch.get())==0,"vision encoding failed");
            for(size_t j=first;j<last;++j) {
                float *data=mtmd_batch_get_output_embd(batch.get(),images[j]); require(data!=nullptr,"missing embeddings");
                size_t n=mtmd_input_chunk_get_n_tokens(images[j])*llama_model_n_embd(model.get());
                encoded.emplace_back(data,data+n);
            } first=last;
        }
        double vision_ms=ms(tv); auto tp=Clock::now(); llama_pos pos=0; size_t index=0;
        for(size_t i=0;i<mtmd_input_chunks_size(chunks.get());++i) {
            auto c=mtmd_input_chunks_get(chunks.get(),i); int rc;
            if(mtmd_input_chunk_get_type(c)==MTMD_INPUT_CHUNK_TYPE_TEXT)
                rc=mtmd_helper_eval_chunk_single(vision.get(),ctx.get(),c,pos,0,1024,i+1==mtmd_input_chunks_size(chunks.get()),&pos);
            else rc=mtmd_helper_decode_image_chunk(vision.get(),ctx.get(),c,encoded.at(index++).data(),pos,0,1024,&pos,nullptr,nullptr);
            require(rc==0,"prefill failed");
        }
        double prefill_ms=ms(tp); auto td=Clock::now();
        std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)> sampler(llama_sampler_init_greedy(),llama_sampler_free);
        const auto vocab=llama_model_get_vocab(model.get()); std::string answer; int count=0; bool stopped=false;
        for(int i=0;i<96;++i) {
            auto tok=llama_sampler_sample(sampler.get(),ctx.get(),-1); llama_sampler_accept(sampler.get(),tok);
            if(llama_vocab_is_eog(vocab,tok)) { stopped=true; break; }
            answer+=piece(vocab,tok); ++count;
            if(i<95) { auto batch=llama_batch_get_one(&tok,1); require(llama_decode(ctx.get(),batch)==0,"decode failed"); }
        }
        std::cout<<"{\"event\":\"response\",\"native_ms\":"<<ms(t)<<",\"vision_ms\":"<<vision_ms
                 <<",\"prefill_ms\":"<<prefill_ms<<",\"decode_ms\":"<<ms(td)<<",\"output_tokens\":"<<count
                 <<",\"finish_reason\":\""<<(stopped?"stop":"length")<<"\",\"text\":\""<<escape(answer)<<"\"}"<<std::endl;
        for(auto bitmap:owned) mtmd_bitmap_free(bitmap);
    }
    return 0;
}
