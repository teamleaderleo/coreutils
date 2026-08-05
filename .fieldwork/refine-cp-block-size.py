#!/usr/bin/env python3
"""Replace the sparse-copy block-size unwrap with checked conversion."""

from pathlib import Path

path = Path("src/uu/cp/src/platform/linux.rs")
text = path.read_text(encoding="utf-8")
old = '''    let blksize = dst_file
        .metadata()
        .map_err(&ctx_err)?
        .blksize()
        .try_into()
        .unwrap();
    sparse_copy_data(&mut src_file, &dst_file, size, blksize, context)
'''
new = '''    let blksize: usize = dst_file
        .metadata()
        .map_err(&ctx_err)?
        .blksize()
        .try_into()
        .map_err(|error| {
            ctx_err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                error,
            ))
        })?;
    sparse_copy_data(&mut src_file, &dst_file, size, blksize.max(1), context)
'''
if text.count(old) != 1:
    raise SystemExit(f"expected one replacement site, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
