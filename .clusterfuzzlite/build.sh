#!/bin/bash -eu

# Hash-pinned runtime dependencies, exported from uv.lock. The project itself
# is bundled from src/ rather than installed, so no build backend is fetched.
pip3 install --require-hashes -r .clusterfuzzlite/requirements.txt

for fuzzer in fuzz/*_fuzzer.py; do
    fuzzer_name="$(basename -s .py "$fuzzer")"
    pyinstaller --distpath "$OUT" --onefile --paths src --name "$fuzzer_name.pkg" "$fuzzer"

    cat > "$OUT/$fuzzer_name" <<EOF
#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
this_dir=\$(dirname "\$0")
ASAN_OPTIONS=\$ASAN_OPTIONS:symbolize=1:external_symbolizer_path=\$this_dir/llvm-symbolizer:detect_leaks=0 \
    "\$this_dir/$fuzzer_name.pkg" "\$@"
EOF
    chmod +x "$OUT/$fuzzer_name"

    corpus_dir="fuzz/corpus/$fuzzer_name"
    corpus_files=("$corpus_dir"/*)
    if [ -e "${corpus_files[0]}" ]; then
        zip -j "$OUT/${fuzzer_name}_seed_corpus.zip" "${corpus_files[@]}"
    fi
done
