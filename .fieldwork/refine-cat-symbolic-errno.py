#!/usr/bin/env python3
"""Replace path-based cat open-error refinement with symbolic errno mapping."""

from pathlib import Path


path = Path("src/uu/cat/src/cat.rs")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        '''use std::ffi::OsString;
use std::fs::{File, metadata};
use std::io::{self, BufWriter, ErrorKind, IsTerminal, Read, Write};
''',
        '''use std::ffi::OsString;
use std::fs::File;
#[cfg(not(unix))]
use std::fs::metadata;
use std::io::{self, BufWriter, ErrorKind, IsTerminal, Read, Write};
''',
    ),
    (
        '''#[cfg(unix)]
fn map_open_error(path: &OsString, error: io::Error) -> CatError {
    // Successful inputs are classified from their opened descriptor. A failed
    // open consumes no file, so a path lookup here is used only to preserve the
    // established cross-Unix socket diagnostic.
    if metadata(path).is_ok_and(|metadata| metadata.file_type().is_socket()) {
        return CatError::NoSuchDeviceOrAddress;
    }

    #[cfg(not(any(target_os = "macos", target_os = "freebsd")))]
    let too_many_symlink_code = 40;
    #[cfg(any(target_os = "macos", target_os = "freebsd"))]
    let too_many_symlink_code = 62;
    if error.raw_os_error() == Some(too_many_symlink_code) {
        CatError::TooManySymlinks
    } else {
        error.into()
    }
}
''',
        '''#[cfg(unix)]
fn map_open_error(error: io::Error) -> CatError {
    match rustix::io::Errno::from_io_error(&error) {
        Some(rustix::io::Errno::NXIO) => CatError::NoSuchDeviceOrAddress,
        Some(rustix::io::Errno::LOOP) => CatError::TooManySymlinks,
        _ => error.into(),
    }
}
''',
    ),
    (
        '''    let file = File::open(path).map_err(|error| map_open_error(path, error))?;
''',
        '''    let file = File::open(path).map_err(map_open_error)?;
''',
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one replacement site, found {count}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
