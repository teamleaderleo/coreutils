#!/usr/bin/env python3
"""Apply the controlled cp sparse early-EOF candidate.

The replacement is exact and single-occurrence so source drift fails closed.
"""

from pathlib import Path


path = Path("src/uu/cp/src/platform/linux.rs")
text = path.read_text(encoding="utf-8")
old = '''/// Perform a sparse copy from one file to another.
/// Creates a holes for large sequences of zeros in `non_sparse_files`, used for `--sparse=always`
fn sparse_copy<P>(source: P, dest: P, nofollow: bool, context: &str) -> CopyResult<()>
where
    P: AsRef<Path>,
{
    let mut src_file =
        open_source(&source, nofollow).map_err(|e| CpError::IoErrContext(e, context.to_owned()))?;
    let dst_file = create_dest_restrictive(&dest, false).map_err(|e| {
        CpError::IoErrContext(
            e,
            translate!("cp-error-cannot-create-regular-file", "path" => dest.as_ref().quote()),
        )
    })?;

    let ctx_err = |e: std::io::Error| CpError::IoErrContext(e, context.to_owned());

    let size: usize = src_file
        .metadata()
        .map_err(&ctx_err)?
        .size()
        .try_into()
        .unwrap();
    ftruncate(&dst_file, size.try_into().unwrap())
        .map_err(|e| CpError::IoErrContext(e.into(), context.to_owned()))?;

    let blksize = dst_file.metadata().map_err(&ctx_err)?.blksize();
    let mut buf: Vec<u8> = vec![0; blksize.try_into().unwrap()];
    let mut current_offset: usize = 0;

    // TODO Perhaps we can employ the "fiemap ioctl" API to get the
    // file extent mappings:
    // https://www.kernel.org/doc/html/latest/filesystems/fiemap.html
    while current_offset < size {
        let this_read = src_file.read(&mut buf).map_err(&ctx_err)?;
        let buf = &buf[..this_read];
        if buf.iter().any(|&x| x != 0) {
            dst_file
                .write_all_at(buf, current_offset.try_into().unwrap())
                .map_err(&ctx_err)?;
        }
        current_offset += this_read;
    }
    Ok(())
}
'''
new = '''/// Copy sparse data up to a size snapshot, shrinking the destination if the
/// source reaches EOF before that snapshot.
fn sparse_copy_data<R: Read>(
    src_file: &mut R,
    dst_file: &std::fs::File,
    size: u64,
    blksize: usize,
    context: &str,
) -> CopyResult<()> {
    let ctx_err = |e: std::io::Error| CpError::IoErrContext(e, context.to_owned());
    let mut buf: Vec<u8> = vec![0; blksize];
    let mut current_offset: u64 = 0;

    // TODO Perhaps we can employ the "fiemap ioctl" API to get the
    // file extent mappings:
    // https://www.kernel.org/doc/html/latest/filesystems/fiemap.html
    while current_offset < size {
        let this_read = src_file.read(&mut buf).map_err(&ctx_err)?;
        if this_read == 0 {
            // The source was shortened after its metadata size was captured.
            // Remove the destination's stale pre-sized tail and finish at the
            // amount of data the open source stream actually supplied.
            ftruncate(dst_file, current_offset)
                .map_err(|e| CpError::IoErrContext(e.into(), context.to_owned()))?;
            break;
        }

        let buf = &buf[..this_read];
        if buf.iter().any(|&x| x != 0) {
            dst_file
                .write_all_at(buf, current_offset)
                .map_err(&ctx_err)?;
        }
        current_offset += this_read as u64;
    }
    Ok(())
}

/// Perform a sparse copy from one file to another.
/// Creates holes for large sequences of zeros in non-sparse files, used for `--sparse=always`.
fn sparse_copy<P>(source: P, dest: P, nofollow: bool, context: &str) -> CopyResult<()>
where
    P: AsRef<Path>,
{
    let mut src_file =
        open_source(&source, nofollow).map_err(|e| CpError::IoErrContext(e, context.to_owned()))?;
    let dst_file = create_dest_restrictive(&dest, false).map_err(|e| {
        CpError::IoErrContext(
            e,
            translate!("cp-error-cannot-create-regular-file", "path" => dest.as_ref().quote()),
        )
    })?;

    let ctx_err = |e: std::io::Error| CpError::IoErrContext(e, context.to_owned());
    let size = src_file.metadata().map_err(&ctx_err)?.size();
    ftruncate(&dst_file, size)
        .map_err(|e| CpError::IoErrContext(e.into(), context.to_owned()))?;

    let blksize = dst_file
        .metadata()
        .map_err(&ctx_err)?
        .blksize()
        .try_into()
        .unwrap();
    sparse_copy_data(&mut src_file, &dst_file, size, blksize, context)
}

#[cfg(test)]
mod tests {
    use super::sparse_copy_data;
    use rustix::fs::ftruncate;
    use std::io::{Cursor, Read, Seek, SeekFrom};
    use tempfile::tempfile;

    #[test]
    fn sparse_copy_data_truncates_destination_on_early_eof() {
        let input = b"copied bytes";
        let declared_size = input.len() as u64 + 4096;
        let mut source = Cursor::new(&input[..]);
        let mut destination = tempfile().unwrap();
        ftruncate(&destination, declared_size).unwrap();

        sparse_copy_data(&mut source, &destination, declared_size, 4, "test").unwrap();

        assert_eq!(destination.metadata().unwrap().len(), input.len() as u64);
        destination.seek(SeekFrom::Start(0)).unwrap();
        let mut copied = Vec::new();
        destination.read_to_end(&mut copied).unwrap();
        assert_eq!(copied, input);
    }
}
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"{path}: expected one sparse_copy replacement site, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
