# Known limitations

1. **Experimental local diagnostic model.** The user supplies weights and
   chooses the model explicitly. Advice is advisory and depends on those weights.
   See [benchmarks](docs/benchmarks.md).
2. **The 15-model/1,500-agent path is tested with fixtures.** It demonstrates
   registration, state and message routing, not 1,500 concurrent inference calls.
3. **Provider catalog is 44 profiles, not 300.** The 300 target is not claimed.
4. **Most cloud provider protocols need dedicated adapters.** Anthropic, Gemini,
   Bedrock, Cohere, Replicate and Cloudflare are listed but not silently treated
   as OpenAI.
5. **Quantization is mostly metadata.** GGUF/IQ profiles are represented; GPTQ,
   AWQ, EXL2, HQQ, AQLM and VPTQ are marked `CONFIGURED_NOT_TESTED`. No
   conversion or quality measurement was performed.
6. **No computer twin.** GUI automation, VM sandboxing, screenshots and desktop
   control are not implemented.
7. **No full upstream source copy.** Ten repositories were cloned for study; no
   upstream code was copied. Three checkouts hit Windows path-length limits.
8. **No automatic merge.** Parallel solutions are read-only; write-set conflicts
   are rejected or reported, not semantically merged.
9. **Project checks are not OS-sandboxed.** They run local argv with timeouts and
   output limits; a malicious `.loopsieve.json` is still dangerous.
10. **Studio/WebUI compatibility modules remain.** The terminal is the recommended
    surface; browser UI is not the product.
11. **No 10,000-star or competitor-superiority claim.** No user study or
    comparative benchmark supports such a claim.
