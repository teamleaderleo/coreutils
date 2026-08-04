#!/usr/bin/env python3
"""Apply the controlled sort FIFO preflight candidate.

All replacements are exact and single-occurrence so source drift fails closed.
"""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement site, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


source = Path("src/uu/sort/src/sort.rs")
replace_once(
    source,
    '''use std::path::Path;
use std::path::PathBuf;
''',
    '''use std::path::Path;
use std::path::PathBuf;
#[cfg(unix)]
use std::os::unix::fs::FileTypeExt;
''',
)
replace_once(
    source,
    '''const STDIN_FILE: &str = "-";

/// Legacy `+POS1 [-POS2]` syntax is permitted unless `_POSIX2_VERSION` is in
''',
    '''const STDIN_FILE: &str = "-";

fn should_preflight_input(path: &OsStr) -> bool {
    if path == STDIN_FILE {
        return true;
    }

    #[cfg(unix)]
    {
        // A FIFO open is a consuming handshake with its writer, not a harmless
        // availability probe. Defer FIFOs to the real read pass so the writer's
        // one session is not attached to a temporary handle and discarded.
        return !std::fs::metadata(Path::new(path))
            .is_ok_and(|metadata| metadata.file_type().is_fifo());
    }

    #[cfg(not(unix))]
    true
}

/// Legacy `+POS1 [-POS2]` syntax is permitted unless `_POSIX2_VERSION` is in
''',
)
replace_once(
    source,
    '''    // Verify that we can open all input files.
    // It is the correct behavior to close all files afterwards,
    // and to reopen them at a later point. This is different from how the output file is handled,
    // probably to prevent running out of file descriptors.
    for file in &files {
        open(file)?;
    }
''',
    '''    // Verify ordinary inputs before sorting so errors such as a missing
    // file are reported before waiting on a stream. FIFOs are deliberately
    // excluded: opening and dropping one would consume its writer session,
    // discard unread bytes, and make the real read block on a second writer.
    for file in &files {
        if should_preflight_input(file) {
            open(file)?;
        }
    }
''',
)

tests = Path("tests/by-util/test_sort.rs")
replace_once(
    tests,
    '''use std::env;
use std::fmt::Write as FmtWrite;
#[cfg(unix)]
use std::process::Command;
use std::time::Duration;
''',
    '''use std::env;
use std::fmt::Write as FmtWrite;
#[cfg(unix)]
use std::fs::OpenOptions;
#[cfg(unix)]
use std::io::Write;
#[cfg(unix)]
use std::process::Command;
use std::time::Duration;
''',
)
replace_once(
    tests,
    '''use uutests::at_and_ucmd;
use uutests::new_ucmd;
use uutests::util::TestScenario;
''',
    '''use uutests::at_and_ucmd;
use uutests::new_ucmd;
use uutests::util::TestScenario;
use uutests::util_name;
''',
)
replace_once(
    tests,
    '''#[test]
fn test_buffer_sizes() {
''',
    '''#[test]
#[cfg(unix)]
fn test_named_fifo_unterminated_line_is_consumed_once() {
    let scene = TestScenario::new(util_name!());
    let fifo = scene.fixtures.plus("input.fifo");
    nix::unistd::mkfifo(&fifo, nix::sys::stat::Mode::S_IRUSR | nix::sys::stat::Mode::S_IWUSR)
        .unwrap();

    let writer = std::thread::spawn(move || {
        let mut file = OpenOptions::new().write(true).open(fifo).unwrap();
        file.write_all(b"hello").unwrap();
    });

    scene
        .ucmd()
        .timeout(Duration::from_secs(5))
        .arg("input.fifo")
        .succeeds()
        .stdout_only("hello\\n");
    writer.join().unwrap();
}

#[test]
#[cfg(unix)]
fn test_missing_file_is_reported_before_waiting_on_fifo() {
    let scene = TestScenario::new(util_name!());
    let fifo = scene.fixtures.plus("input.fifo");
    nix::unistd::mkfifo(&fifo, nix::sys::stat::Mode::S_IRUSR | nix::sys::stat::Mode::S_IWUSR)
        .unwrap();

    scene
        .ucmd()
        .timeout(Duration::from_secs(2))
        .arg("input.fifo")
        .arg("missing")
        .fails_with_code(2)
        .stderr_only("sort: cannot read: missing: No such file or directory\\n");
}

#[test]
fn test_buffer_sizes() {
''',
)
