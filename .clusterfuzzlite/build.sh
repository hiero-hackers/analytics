#!/bin/bash -eu

PDM_BUILD_SCM_VERSION=0.0.0 pip3 install .

for fuzzer in fuzz/*_fuzzer.py; do
    fuzzer_name="$(basename -s .py "$fuzzer")"
    pyinstaller --distpath "$OUT" --onefile --name "$fuzzer_name.pkg" "$fuzzer"

    cat > "$OUT/$fuzzer_name" <<EOF
#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
this_dir=\$(dirname "\$0")
ASAN_OPTIONS=\$ASAN_OPTIONS:symbolize=1:external_symbolizer_path=\$this_dir/llvm-symbolizer:detect_leaks=0 \
    \$this_dir/$fuzzer_name.pkg \$@
EOF
    chmod +x "$OUT/$fuzzer_name"
done

zip -j "$OUT/hip_frontmatter_fuzzer_seed_corpus.zip" fuzz/corpus/hip_frontmatter_fuzzer/*
